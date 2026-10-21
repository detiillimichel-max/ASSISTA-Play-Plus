"use strict";
const tf = require("@tensorflow/tfjs-node");
const nsfwjs = require("nsfwjs");
let modelPromise;
function getModel() {
  if (!modelPromise) { modelPromise = nsfwjs.load(); modelPromise.catch(() => { modelPromise = undefined; }); }
  return modelPromise;
}
async function fetchImageBuffer(url, maxBytes = 8 * 1024 * 1024) {
  const parsed = new URL(url);
  const host = parsed.hostname.toLowerCase();
  const allowedExact = new Set([
    "archive.org", "www.archive.org", "images.pexels.com", "cdn.pixabay.com", "static-cdn.jtvnw.net", "i.vimeocdn.com",
    "upload.wikimedia.org", "commons.wikimedia.org", "images-assets.nasa.gov",
    "images.nasa.gov", "loc.gov", "www.loc.gov", "europeana.eu",
    "api.europeana.eu", "dvidshub.net", "www.dvidshub.net", "media.defense.gov"
  ]);
  const allowedSuffixes = [".loc.gov", ".europeana.eu", ".dvidshub.net"];
  const peertubeHosts = String(process.env.PEERTUBE_INSTANCES || "").split(",")
    .map(value => { try { return new URL(value.trim()).hostname.toLowerCase(); } catch { return ""; } })
    .filter(Boolean);
  const hostAllowed = allowedExact.has(host) || allowedSuffixes.some(suffix => host.endsWith(suffix)) || peertubeHosts.includes(host);
  if (parsed.protocol !== "https:" || !hostAllowed) throw new Error("URL de imagem fora da lista permitida");
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { signal: controller.signal, headers: { "User-Agent": "ASSISTA-Plus-Family-Moderation/1.0" } });
    if (!response.ok) throw new Error("Imagem HTTP " + response.status);
    const type = (response.headers.get("content-type") || "").toLowerCase();
    if (!type.startsWith("image/")) throw new Error("Resposta não é uma imagem");
    if (Number(response.headers.get("content-length") || 0) > maxBytes) throw new Error("Imagem acima do limite de tamanho");
    const buffer = Buffer.from(await response.arrayBuffer());
    if (!buffer.length || buffer.length > maxBytes) throw new Error("Imagem vazia ou acima do limite");
    return buffer;
  } finally { clearTimeout(timer); }
}
function decide(predictions) {
  if (!Array.isArray(predictions) || !predictions.length) return { approved: false, reason: "PREDICOES_INVALIDAS" };
  const scores = Object.fromEntries(predictions.map(p => [p.className, Number(p.probability)]));
  for (const p of predictions) if (!Number.isFinite(Number(p.probability)) || p.probability < 0 || p.probability > 1) return { approved: false, reason: "PREDICAO_INVALIDA", scores };
  const isBad = (scores.Porn ?? 0) > 0.25 || (scores.Sexy ?? 0) > 0.5 || (scores.Hentai ?? 0) > 0.25;
  if (isBad) {
    const reason = (scores.Porn ?? 0) > 0.25 ? "PORN" : (scores.Sexy ?? 0) > 0.5 ? "SEXY" : "HENTAI";
    return { approved: false, reason, scores };
  }
  return { approved: true, reason: "PASSOU_LIMIARES", scores };
}
async function analisarImagemBuffer(buffer) {
  if (!Buffer.isBuffer(buffer) || !buffer.length) return { approved: false, reason: "IMAGEM_AUSENTE" };
  let tensor;
  try {
    const model = await getModel(); tensor = tf.node.decodeImage(buffer, 3);
    if (tensor.shape.length !== 3 || tensor.shape[0] < 1 || tensor.shape[1] < 1) return { approved: false, reason: "IMAGEM_INVALIDA" };
    return decide(await model.classify(tensor));
  } catch (error) {
    return { approved: false, reason: "ANALISE_INDISPONIVEL", error: String(error?.message || error).slice(0,180) };
  } finally { if (tensor) tensor.dispose(); }
}
async function analisarUrl(url) {
  try { return await analisarImagemBuffer(await fetchImageBuffer(url)); }
  catch (error) { return { approved: false, reason: "IMAGEM_INDISPONIVEL", error: String(error?.message || error).slice(0,180) }; }
}
module.exports = { analisarImagemBuffer, analisarUrl, decide };
