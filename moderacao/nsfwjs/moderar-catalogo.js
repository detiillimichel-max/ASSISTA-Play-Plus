"use strict";
const fs = require("node:fs/promises");
const path = require("node:path");
const { analisarUrl } = require("./classificar");
const root = path.resolve(__dirname, "../..");
const catalogPath = path.join(root, "catalog.json");
const categoryDir = path.join(root, "catalog");
const policyPath = path.join(root, "moderacao", "politica.json");
const blocklistPath = path.join(root, "moderacao", "blocklist.json");
const requestedConcurrency = Number(process.env.NSFW_CONCURRENCY) || 3;
const concurrency = Math.max(1, Math.min(4, requestedConcurrency));
let policy = { version: "unknown", visualPolicy: {} };
let persistentBlocklist = new Set();
const BLOCKED_COLLECTIONS = ["forbidden-cinema","forbidden_cinema","adults-only","adult_films","erotica","pinup","pin-up","burlesque","playboy","hustler","sexploitation","nudist","adults_only"];
const BLOCKED_PATTERNS = [
  /\\b(?:porn|porno|pornography|pornographic|xxx|hentai)\\b/i,
  /\\b(?:nudes?|nudity|naked|topless|nudist|nudism|naturist)\\b/i,
  /\\b(?:erotic|erotica|erotism|fetish|bdsm|bondage|sexploitation|stag film)\\b/i,
  /\\b(?:burlesque|pin[ -]?up|striptease|adults? only|hardcore|softcore)\\b/i,
  /\\b(?:sexo|er[oó]tic[oa]s?|pelad[oa]s?|pornografia|pornogr[aá]fic[oa]s?|nudez|conte[uú]do sexual|conte[uú]do adulto)\\b/i,
  /\\b(?:sex tape|sex film|sex video|sexual content|explicit sex|adult film)\\b/i
];
function normalize(value) {
  return String(value ?? "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[_-]+/g, " ").replace(/[^a-z0-9]+/g, " ").trim();
}
function metadataText(item) {
  return [item.title,item.name,item.description,item.creator,item.collection,item.collections,item.subject,item.tags,item.keywords,item.identifier,item.source,item.publisher,item.notes]
    .flatMap(value => Array.isArray(value) ? value : [value]).filter(value => value != null).join(" ");
}
function blockedByMetadata(item) {
  if (persistentBlocklist.has(String(item.identifier || ""))) return "BLOCKLIST_PERSISTENTE";
  const normalized = " " + normalize(metadataText(item)) + " ";
  const collections = [item.collection,item.collections,item.identifier]
    .flatMap(value => Array.isArray(value) ? value : [value]).filter(Boolean).map(normalize);
  if (collections.some(value => BLOCKED_COLLECTIONS.some(term => value.includes(normalize(term))))) return "BLOCKLIST_COLECAO";
  const term = BLOCKED_PATTERNS.find(pattern => pattern.test(metadataText(item)));
  return term ? "BLOCKLIST_TEXTO:" + term.source : null;
}
async function readJson(file) { return JSON.parse(await fs.readFile(file, "utf8")); }
async function writeJson(file, data) { await fs.writeFile(file, JSON.stringify(data, null, 2) + "\n", "utf8"); }
async function mapLimit(items, limit, fn) {
  const results = new Array(items.length); let next = 0;
  async function worker() {
    while (true) {
      const i = next++;
      if (i >= items.length) return;
      try { results[i] = await fn(items[i], i); }
      catch (error) {
        results[i] = { item: items[i], approved: false, reason: "ERRO_ITEM", error: String(error?.message || error).slice(0,180) };
        console.log("REJEITADO por erro isolado:", items[i]?.identifier || "(sem identifier)", results[i].error);
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}
async function main() {
  if (String(process.env.PAUSE_MODERATION || "").toLowerCase() === "true") {
    console.log("MODERATION_PAUSED: NSFWJS não será executado nesta coleta.");
    return;
  }
  try { policy = JSON.parse(await fs.readFile(policyPath, "utf8")); } catch {}
  try {
    const data = JSON.parse(await fs.readFile(blocklistPath, "utf8"));
    persistentBlocklist = new Set((data.items || []).map(item => String(item.identifier)).filter(Boolean));
  } catch {}
  const catalog = await readJson(catalogPath);
  if (!catalog || !Array.isArray(catalog.items) || !catalog.items.length) throw new Error("catalog.json ausente, inválido ou vazio; moderação cancelada.");
  const seen = new Set();
  const unique = catalog.items.filter(item => {
    if (!item || !item.identifier || seen.has(String(item.identifier))) return false;
    seen.add(String(item.identifier)); return true;
  });
  if (unique.length !== catalog.items.length) console.log("Itens duplicados/inválidos removidos:", catalog.items.length - unique.length);
  console.log("Analisando capas com NSFWJS:", unique.length, "itens; concorrência:", concurrency);
  const decisions = await mapLimit(unique, concurrency, async item => {
    const blockedReason = blockedByMetadata(item);
    if (blockedReason) {
      console.log("REJEITADO pela blocklist:", item.identifier, blockedReason);
      return { item, approved: false, reason: blockedReason };
    }
    // Archive.org oferece uma miniatura padrão pelo identifier; usa-a quando
    // o registro não trouxer thumbnail, thumb ou cover explicitamente.
    const isArchiveItem = !item.source || String(item.source).toLowerCase().includes("archive");
    // Fail-closed: apenas allowlist explícita pode dispensar análise visual.
    // moderationPolicy enviada pelo coletor é validada, nunca aceita cegamente.
    // No perfil familiar estrito, fonte institucional não dispensa a análise visual.
    const suppliedThumbnail = item.thumbnail || item.thumb || item.cover;
    const imageUrl = String(
      suppliedThumbnail || (isArchiveItem
        ? ("https://archive.org/services/img/" + encodeURIComponent(String(item.source_id || item.identifier).replace(/^internet-archive:/, "")))
        : "")
    ).trim();
    if (!imageUrl) {
      console.log("REJEITADO pela moderação visual:", item.identifier, "MINIATURA_AUSENTE");
      return { item, approved: false, reason: "MINIATURA_AUSENTE" };
    }
    const result = await analisarUrl(imageUrl);
    if (result.approved) return { item, approved: true, reason: result.reason };
    console.log("REJEITADO pela moderação visual:", item.identifier, result.reason);
    return { item, approved: false, reason: result.reason };
  });
  const approvedIds = new Set(decisions.filter(x => x.approved).map(x => String(x.item.identifier)));
  const approvedItems = unique.filter(x => approvedIds.has(String(x.identifier)));
  const reasonCounts = {};
  for (const decision of decisions) {
    if (!decision.approved) {
      const reason = String(decision.reason || "REJEITADO_SEM_MOTIVO");
      reasonCounts[reason] = (reasonCounts[reason] || 0) + 1;
    }
  }
  console.log("Resumo dos motivos de rejeição:", JSON.stringify(reasonCounts, null, 2));
  const technicalReasons = new Set(["ANALISE_INDISPONIVEL", "IMAGEM_INDISPONIVEL", "ERRO_ITEM"]);
  const technicalFailures = decisions.filter(x => !x.approved && technicalReasons.has(String(x.reason || ""))).length;
  const technicalRatio = decisions.length ? technicalFailures / decisions.length : 1;
  console.log("Diagnóstico técnico da moderação:", JSON.stringify({ total: decisions.length, technicalFailures, technicalFailurePercent: Math.round(technicalRatio * 100) }));
  const maxTechnicalRatio = Math.max(0, Math.min(1, Number(process.env.NSFW_MAX_TECHNICAL_FAILURE_RATIO) || 0.30));
  if (technicalRatio > maxTechnicalRatio) {
    throw new Error("Falhas técnicas de moderação acima do limite: " + Math.round(technicalRatio * 100) + "% > " + Math.round(maxTechnicalRatio * 100) + "%. Catálogo anterior preservado.");
  }
  if (!approvedItems.length) {
    throw new Error(
      "Nenhum item passou na moderação visual/textual. A publicação foi bloqueada para preservar o catálogo anterior. " +
      "Motivos: " + JSON.stringify(reasonCounts)
    );
  }
  const checkedAt = new Date().toISOString();
  for (const item of approvedItems) {
    item.safety = "approved";
    item.ageRating = "family";
    item.moderationPolicyVersion = policy.version || "unknown";
    item.moderatedAt = checkedAt;
  }
  catalog.items = approvedItems; catalog.count = approvedItems.length;
  catalog.visualModeration = { engine: "NSFWJS + blocklist textual", policyVersion: policy.version || "unknown", checked: decisions.length, approved: approvedItems.length, rejected: decisions.length - approvedItems.length, rejectionReasons: reasonCounts, checkedAt, scope: "metadata-and-thumbnail-only", note: "A aprovação da capa não garante que o vídeo inteiro seja adequado." };
  if (Array.isArray(catalog.categories)) catalog.categories = catalog.categories.map(category => ({ ...category, count: approvedItems.filter(item => item.category === category.key).length }));
  await writeJson(catalogPath, catalog);
  const files = await fs.readdir(categoryDir).catch(() => []);
  for (const filename of files.filter(name => name.endsWith(".json"))) {
    const file = path.join(categoryDir, filename); let categoryData;
    try { categoryData = await readJson(file); } catch { continue; }
    if (!Array.isArray(categoryData.items)) continue;
    categoryData.items = categoryData.items.filter(item => approvedIds.has(String(item.identifier)));
    categoryData.count = categoryData.items.length;
    categoryData.visualModeration = { engine: "NSFWJS + blocklist textual", checked: decisions.length, approved: categoryData.items.length, rejected: decisions.length - categoryData.items.length, checkedAt };
    categoryData.updatedAt = catalog.updatedAt || checkedAt;
    await writeJson(file, categoryData);
  }
  console.log(JSON.stringify({ checked: decisions.length, approved: approvedItems.length, rejected: decisions.length - approvedItems.length, remaining: approvedItems.length }, null, 2));
}
main().catch(error => { console.error("ERRO na moderação visual:", error?.stack || error); process.exitCode = 1; });
