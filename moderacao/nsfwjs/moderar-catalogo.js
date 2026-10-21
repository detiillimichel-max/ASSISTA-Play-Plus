"use strict";
const fs = require("node:fs/promises");
const path = require("node:path");
const { analisarUrl } = require("./classificar");
const root = path.resolve(__dirname, "../..");
const catalogPath = path.join(root, "catalog.json");
const categoryDir = path.join(root, "catalog");
const concurrency = Math.max(1, Math.min(4, Number(process.env.NSFW_CONCURRENCY || 3)));
const BLOCKED_COLLECTIONS = ["forbidden-cinema","forbidden_cinema","adults-only","adult_films","erotica","pinup","pin-up","burlesque","playboy","hustler","sexploitation","nudist","adults_only"];
const BLOCKED_TERMS = ["forbidden cinema","adults only","erotica","erotic","burlesque","pinup","pin-up","nude","nudist","striptease"];
function normalize(value) {
  return String(value ?? "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[_-]+/g, " ").replace(/[^a-z0-9]+/g, " ").trim();
}
function metadataText(item) {
  return [item.title,item.name,item.description,item.creator,item.collection,item.collections,item.subject,item.identifier,item.source,item.publisher,item.notes]
    .flatMap(value => Array.isArray(value) ? value : [value]).filter(value => value != null).join(" ");
}
function blockedByMetadata(item) {
  const normalized = " " + normalize(metadataText(item)) + " ";
  const collections = [item.collection,item.collections,item.identifier]
    .flatMap(value => Array.isArray(value) ? value : [value]).filter(Boolean).map(normalize);
  if (collections.some(value => BLOCKED_COLLECTIONS.some(term => value.includes(normalize(term))))) return "BLOCKLIST_COLECAO";
  const term = BLOCKED_TERMS.find(value => normalized.includes(" " + normalize(value) + " "));
  return term ? "BLOCKLIST_TEXTO:" + term : null;
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
  const technicalReasons = new Set(["ANALISE_INDISPONIVEL", "IMAGEM_INDISPONIVEL", "MINIATURA_AUSENTE", "IMAGEM_AUSENTE", "ERRO_ITEM"]);
  const technicalFailures = decisions.filter(x => !x.approved && technicalReasons.has(String(x.reason || ""))).length;
  const technicalRatio = decisions.length ? technicalFailures / decisions.length : 1;
  console.log("Diagnóstico técnico da moderação:", JSON.stringify({ total: decisions.length, technicalFailures, technicalFailurePercent: Math.round(technicalRatio * 100) }));
  // Uma falha técnica em massa não é evidência de conteúdo impróprio.
  // Interrompe a publicação para o workflow restaurar o último catálogo válido.
  const maxTechnicalRatio = Math.max(0.05, Math.min(0.5, Number(process.env.NSFW_MAX_TECHNICAL_FAILURE_RATIO || 0.2)));
  if (technicalRatio > maxTechnicalRatio) {
    throw new Error("Moderação inconclusiva: " + technicalFailures + "/" + decisions.length + " itens falharam tecnicamente. Publicação cancelada para preservar o catálogo anterior.");
  }
  if (!approvedItems.length) {
    throw new Error(
      "Nenhum item passou na moderação visual/textual. A publicação foi bloqueada para preservar o catálogo anterior. " +
      "Motivos: " + JSON.stringify(reasonCounts)
    );
  }
  const checkedAt = new Date().toISOString();
  catalog.items = approvedItems; catalog.count = approvedItems.length;
  catalog.visualModeration = { engine: "NSFWJS + blocklist textual", checked: decisions.length, approved: approvedItems.length, rejected: decisions.length - approvedItems.length, rejectionReasons: reasonCounts, checkedAt, scope: "metadata-and-thumbnail-only", note: "A aprovação da capa não garante que o vídeo inteiro seja adequado." };
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
