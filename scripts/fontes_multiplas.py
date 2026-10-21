"""Coletores independentes de fontes públicas de vídeo para ASSISTA+.

Cada adaptador falha isoladamente. Saída normalizada para o esquema atual do catálogo.
Fontes sem endpoint oficial/automatização autorizada não são raspadas.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = "ASSISTA-Plus-Catalog/1.0 (public media catalog; contact: repository maintainer)"
TIMEOUT = int(os.getenv("SOURCE_TIMEOUT_SECONDS", "15"))
MAX_PER_SOURCE = max(100, int(os.getenv("MAX_ITEMS_PER_SOURCE", "120")))
METRICS = {}

def request_json(url, headers=None):
    req_headers = {"User-Agent": UA, "Accept": "application/json"}
    req_headers.update(headers or {})
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        content_type = (response.headers.get("Content-Type") or "").lower()
        body = response.read(5 * 1024 * 1024 + 1)
        if len(body) > 5 * 1024 * 1024:
            raise ValueError("resposta excedeu 5 MB")
        if "json" not in content_type and not body.lstrip().startswith((b"{", b"[")):
            raise ValueError("resposta não é JSON")
        return json.loads(body.decode("utf-8"))

def qurl(base, params):
    return base + "?" + urllib.parse.urlencode(params, doseq=True)

def clean(value):
    if isinstance(value, list):
        return ", ".join(str(x) for x in value if x is not None)
    return str(value or "").strip()

def classify(text):
    s = (text or "").lower()
    if any(w in s for w in ("cartoon", "animation", "animated", "anime", "puppet")):
        return "desenhos"
    if any(w in s for w in ("documentary", "documentário", "documentary film")):
        return "documentarios"
    if any(w in s for w in ("science", "space", "nasa", "astronomy", "planet", "engineering", "education", "lecture", "course")):
        return "ciencia"
    if any(w in s for w in ("history", "historical", "historic", "war archive", "heritage")):
        return "historia"
    if any(w in s for w in ("concert", "music", "musical", "orchestra", "performance")):
        return "musica"
    if any(w in s for w in ("comedy", "comedies", "humor", "funny")):
        return "comedia"
    if any(w in s for w in ("series", "episode", "serial", "television")):
        return "series"
    return "filmes"

def item(source, source_id, title, video_url, thumbnail="", page_url="", description="", creator="", license_name="", license_url="", mime="", category=None, embed_url=""):
    if not title or not video_url:
        return None
    parsed = urllib.parse.urlparse(video_url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    ident = re.sub(r"[^A-Za-z0-9._:-]+", "-", f"{source}:{source_id}").strip("-")[:240]
    category = category or classify(" ".join((title, description)))
    record = {
        "identifier": ident, "source": source, "source_id": str(source_id),
        "title": title[:500], "description": description[:1600],
        "creator": creator, "category": category, "thumbnail": thumbnail,
        "detailsUrl": page_url or video_url, "sourceUrl": page_url or video_url,
        "license": license_name, "licenseUrl": license_url,
        "mediaType": "embed" if embed_url else "video",
        "mimeType": mime, "collectedAt": datetime.now(timezone.utc).isoformat(),
        "files": [{"name": title[:240], "format": mime or "external video", "size": 0, "url": video_url}],
        "playbackUrl": video_url,
    }
    if embed_url:
        record["embedUrl"] = embed_url
        record["mediaType"] = "embed"
    return record

def safe_call(name, fn):
    stats = {"requests": 0, "found": 0, "accepted": 0, "errors": 0, "status": "ok"}
    METRICS[name] = stats
    try:
        stats["requests"] += 1
        records = fn() or []
        stats["found"] = len(records)
        result, seen = [], set()
        for rec in records:
            if not rec or rec["identifier"] in seen:
                continue
            seen.add(rec["identifier"])
            result.append(rec)
            if len(result) >= MAX_PER_SOURCE:
                break
        stats["accepted"] = len(result)
        return result
    except Exception as exc:
        stats["errors"] += 1
        stats["status"] = "error"
        stats["error"] = str(exc)[:220]
        print("SOURCE_ERROR", name, type(exc).__name__, str(exc)[:180])
        return []

def pexels():
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        METRICS["pexels"] = {"status": "skipped_missing_credentials", "required": "PEXELS_API_KEY"}
        print("SOURCE_SKIPPED pexels missing PEXELS_API_KEY")
        return []
    def run():
        out = []
        for query in ("nature", "science", "space", "animals", "education", "music", "history", "animation"):
            data = request_json(qurl("https://api.pexels.com/videos/search", {"query": query, "per_page": 15, "page": 1}), {"Authorization": key})
            for v in data.get("videos", []):
                files = sorted(v.get("video_files", []), key=lambda f: (f.get("quality") != "hd", f.get("width", 0) < 640))
                chosen = next((f for f in files if f.get("link") and "video" in str(f.get("file_type", "video/")).lower()), None)
                if not chosen: continue
                out.append(item("pexels", v.get("id"), clean(v.get("user", {}).get("name")) + " — vídeo " + str(v.get("id")), chosen["link"], clean(v.get("image")), v.get("url",""), creator=clean(v.get("user",{}).get("name")), mime=chosen.get("file_type","video/mp4"), category=classify(query)))
                if len(out) >= MAX_PER_SOURCE: break
            if len(out) >= MAX_PER_SOURCE: break
            time.sleep(0.35)
        return out
    return safe_call("pexels", run)

def pixabay():
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        METRICS["pixabay"] = {"status": "skipped_missing_credentials", "required": "PIXABAY_API_KEY"}
        print("SOURCE_SKIPPED pixabay missing PIXABAY_API_KEY")
        return []
    def run():
        out = []
        for query in ("nature", "science", "space", "animals", "education", "music", "history", "animation"):
            data = request_json(qurl("https://pixabay.com/api/videos/", {"key": key, "q": query, "per_page": 20, "safesearch": "true"}))
            for v in data.get("hits", []):
                variants = v.get("videos", {})
                chosen = variants.get("large") or variants.get("medium") or variants.get("small")
                if not chosen or not chosen.get("url"): continue
                out.append(item("pixabay", v.get("id"), clean(v.get("tags")) or "Pixabay video", chosen["url"], clean(v.get("picture")), v.get("pageURL",""), creator=str(v.get("user","")), mime="video/mp4", category=classify(query)))
                if len(out) >= MAX_PER_SOURCE: break
            if len(out) >= MAX_PER_SOURCE: break
            time.sleep(0.35)
        return out
    return safe_call("pixabay", run)

def nasa():
    def run():
        out = []
        for query in ("space mission", "planet", "astronomy", "NASA documentary", "astronaut"):
            data = request_json(qurl("https://images-api.nasa.gov/search", {"q": query, "media_type": "video", "page_size": 30}))
            for row in data.get("collection", {}).get("items", []):
                meta = (row.get("data") or [{}])[0]
                links = row.get("links") or []
                thumb = next((x.get("href") for x in links if x.get("rel") == "preview"), "")
                href = ""
                try:
                    assets = request_json(meta.get("nasa_id") and "https://images-api.nasa.gov/asset/" + urllib.parse.quote(meta["nasa_id"], safe=""))
                    href = next((x.get("href") for x in assets.get("collection", {}).get("items", []) if urllib.parse.urlparse(x.get("href","")).path.lower().endswith((".mp4",".webm",".mov"))), "")
                except Exception as exc:
                    print("SOURCE_ITEM_ERROR nasa", str(exc)[:100])
                if href:
                    out.append(item("nasa", meta.get("nasa_id"), clean(meta.get("title")), href, thumb, clean(meta.get("nasa_id")) and "https://images.nasa.gov/details-" + urllib.parse.quote(meta["nasa_id"]), clean(meta.get("description")), clean(meta.get("secondary_creator")), "See NASA asset terms", "https://www.nasa.gov/nasa-brand-center/images-and-media/", "video/mp4", classify(clean(meta.get("title")) + " " + clean(meta.get("description")))))
                if len(out) >= MAX_PER_SOURCE: return out
            time.sleep(0.25)
        return out
    return safe_call("nasa", run)

def wikimedia():
    def run():
        out = []
        for term in ("nature", "space", "science", "history", "animals", "animation", "music"):
            data = request_json(qurl("https://commons.wikimedia.org/w/api.php", {"action":"query","generator":"search","gsrsearch":f"filetype:video {term}","gsrnamespace":6,"gsrlimit":20,"prop":"imageinfo","iiprop":"url|mime|extmetadata","iiurlwidth":480,"format":"json","origin":"*"}))
            for page in (data.get("query",{}).get("pages",{}) or {}).values():
                info = (page.get("imageinfo") or [{}])[0]
                mime = info.get("mime","")
                url = info.get("url","")
                if mime not in ("video/mp4","video/webm","video/ogg") or not url: continue
                ext = info.get("extmetadata",{})
                license_name = clean((ext.get("LicenseShortName") or {}).get("value"))
                license_url = clean((ext.get("LicenseUrl") or {}).get("value"))
                thumb = info.get("thumburl","")
                title = clean(page.get("title")).removeprefix("File:")
                out.append(item("wikimedia-commons", page.get("pageid"), title, url, thumb, "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(page.get("title","").replace(" ","_")), creator=clean((ext.get("Artist") or {}).get("value")), license_name=license_name, license_url=license_url, mime=mime))
                if len(out) >= MAX_PER_SOURCE: return out
            time.sleep(0.4)
        return out
    return safe_call("wikimedia_commons", run)

def europeana():
    key = os.getenv("EUROPEANA_API_KEY")
    if not key:
        METRICS["europeana"] = {"status": "skipped_missing_credentials", "required": "EUROPEANA_API_KEY"}
        print("SOURCE_SKIPPED europeana missing EUROPEANA_API_KEY")
        return []
    def run():
        out = []
        for query in ("video documentary", "historical film", "science film", "animation film", "concert film"):
            data = request_json(qurl("https://api.europeana.eu/record/v2/search.json", {"wskey":key,"query":query,"qf":"TYPE:VIDEO","media":True,"rows":30,"profile":"rich"}))
            for r in data.get("items",[]):
                link = clean(r.get("edmIsShownBy") or r.get("guid"))
                if not link or not link.lower().split("?")[0].endswith((".mp4",".webm",".ogv",".mov")): continue
                rights = clean(r.get("rights"))
                out.append(item("europeana", clean(r.get("id")), clean(r.get("title")), link, clean(r.get("edmPreview")), clean(r.get("guid")), clean(r.get("dcDescription")), clean(r.get("dcCreator")), rights, rights if rights.startswith("http") else "", "video", classify(clean(r.get("title")) + " " + clean(r.get("dcDescription")))))
                if len(out) >= MAX_PER_SOURCE: return out
            time.sleep(0.5)
        return out
    return safe_call("europeana", run)

def dvids():
    key = os.getenv("DVIDS_API_KEY")
    if not key:
        METRICS["dvids"] = {"status": "skipped_missing_credentials", "required": "DVIDS_API_KEY"}
        print("SOURCE_SKIPPED dvids missing DVIDS_API_KEY")
        return []
    def run():
        out = []
        for query in ("space", "aviation", "science", "history", "documentary"):
            data = request_json(qurl("https://api.dvidshub.net/search", {"api_key":key,"type":"video","q":query,"page":1,"page_size":25}))
            rows = data.get("results") or data.get("results_data") or []
            for r in rows:
                url = clean(r.get("download_url") or r.get("video_url") or r.get("stream_url"))
                if not url: continue
                out.append(item("dvids", r.get("id") or r.get("uuid"), clean(r.get("title")), url, clean(r.get("thumbnail_url") or r.get("thumb")), clean(r.get("url") or r.get("detail_url")), clean(r.get("description")), clean(r.get("credit") or r.get("creator")), clean(r.get("rights")), "", "video/mp4"))
                if len(out) >= MAX_PER_SOURCE: return out
            time.sleep(0.5)
        return out
    return safe_call("dvids", run)

def openverse():
    # Openverse's public API primarily indexes images and audio, not a general video catalog.
    # Do not mislabel still images/audio as video.
    METRICS["openverse"] = {"status": "skipped_no_video_endpoint", "note": "API pública não oferece endpoint geral de vídeos reproduzíveis"}
    print("SOURCE_SKIPPED openverse no general video endpoint; won't mislabel images/audio as video")
    return []

def library_of_congress():
    def run():
        out = []
        for query in ("motion pictures", "educational films", "historical films", "science films", "animated films"):
            data = request_json(qurl("https://www.loc.gov/film-and-videos/", {"fo":"json","q":query,"c":30}))
            for r in data.get("results",[]):
                resources = r.get("resources") or []
                candidates = []
                for res in resources:
                    for f in res.get("files",[]) if isinstance(res,dict) else []:
                        u = clean(f.get("url") if isinstance(f,dict) else "")
                        if u.lower().split("?")[0].endswith((".mp4",".webm",".mov",".ogv")): candidates.append(u)
                if not candidates: continue
                title = clean(r.get("title"))
                rights = clean(r.get("rights") or r.get("rights_summary"))
                out.append(item("library-of-congress", clean(r.get("id")), title, candidates[0], clean(r.get("image_url")), clean(r.get("url")), clean(r.get("description")), clean(r.get("contributor")), rights, "", "video", classify(title + " " + clean(r.get("description")))))
                if len(out) >= MAX_PER_SOURCE: return out
            time.sleep(0.4)
        return out
    return safe_call("library_of_congress", run)

def internet_archive_prelinger():
    # Internet Archive main collector already handles archive.org; query its Prelinger collection
    # only to supplement it. Existing identifier deduplication removes duplicates.
    def run():
        out = []
        for query in ('collection:prelinger AND mediatype:movies AND format:MP4',):
            data = request_json(qurl("https://archive.org/advancedsearch.php", {"q":query,"fl[]":["identifier","title","description","creator","licenseurl","year"],"rows":MAX_PER_SOURCE,"page":1,"output":"json"}))
            for d in data.get("response",{}).get("docs",[]):
                ident = clean(d.get("identifier"))
                if not ident: continue
                meta = request_json("https://archive.org/metadata/" + urllib.parse.quote(ident, safe=""))
                files = [f for f in meta.get("files",[]) if clean(f.get("name")).lower().endswith((".mp4",".webm",".ogv",".mov")) and not f.get("private")]
                if not files: continue
                f = sorted(files,key=lambda x:(not clean(x.get("name")).lower().endswith(".mp4"),-int(x.get("size") or 0)))[0]
                video = "https://archive.org/download/" + urllib.parse.quote(ident,safe="") + "/" + urllib.parse.quote(clean(f.get("name")),safe="/")
                out.append(item("internet-archive-prelinger", ident, clean(d.get("title")), video, "https://archive.org/services/img/" + urllib.parse.quote(ident,safe=""), "https://archive.org/details/" + ident, clean(d.get("description")), clean(d.get("creator")), clean(d.get("licenseurl")), clean(d.get("licenseurl")), clean(f.get("format")), classify(clean(d.get("title")) + " " + clean(d.get("description")))))
                if len(out) >= MAX_PER_SOURCE: break
        return out
    return safe_call("prelinger", run)

def peertube():
    # No instance list exists in the inspected repository; do not invent or replace the user's 11 instances.
    raw = os.getenv("PEERTUBE_INSTANCES", "").strip()
    if not raw:
        METRICS["peertube"] = {"status":"skipped_missing_instance_list","note":"Nenhuma lista das 11 instâncias foi encontrada no repositório; definir PEERTUBE_INSTANCES após recuperar a lista original."}
        print("SOURCE_SKIPPED peertube no existing 11-instance list found; no instances invented")
        return []
    def run():
        out = []
        instances = [x.strip().rstrip("/") for x in re.split(r"[,;\\r\\n]+", raw) if x.strip()]
        for host in instances[:11]:
            try:
                data = request_json(qurl(host + "/api/v1/videos", {"count":20,"sort":"-publishedAt","isLocal":True,"nsfw":"false"}))
                for v in data.get("data",[]):
                    url = clean(v.get("files", [{}])[0].get("fileUrl")) if v.get("files") else ""
                    if not url: continue
                    out.append(item("peertube", str(host) + ":" + str(v.get("uuid") or v.get("id")), clean(v.get("name")), url, (("https://" + urllib.parse.urlparse(host).netloc + clean(v.get("thumbnailPath"))) if clean(v.get("thumbnailPath")).startswith("/") else clean(v.get("thumbnailPath"))), host + "/videos/watch/" + clean(v.get("uuid")), clean(v.get("description")), clean(v.get("account",{}).get("displayName")), clean(v.get("licence",{}).get("label")), "", "video", classify(clean(v.get("name")) + " " + clean(v.get("description")))))
                    if len(out) >= MAX_PER_SOURCE: return out
                time.sleep(1)
            except Exception as exc:
                print("SOURCE_INSTANCE_ERROR peertube", host, str(exc)[:140])
        return out
    return safe_call("peertube", run)

def dpla():
    key = os.getenv("DPLA_API_KEY")
    if not key:
        METRICS["dpla"] = {"status":"skipped_missing_credentials","required":"DPLA_API_KEY"}
        print("SOURCE_SKIPPED dpla missing DPLA_API_KEY")
        return []
    def run():
        out = []
        for query in ("moving image science", "educational film", "historical film", "animation", "space documentary", "music performance"):
            data = request_json(qurl("https://api.dp.la/v2/items", {"q":query,"page_size":100,"page":1,"api_key":key}))
            for row in data.get("docs", []):
                source = row.get("sourceResource") or {}
                title = clean(source.get("title"))
                obj = row.get("object") or ""
                shown = row.get("isShownAt") or ""
                candidates = [u for u in (obj, shown) if isinstance(u,str) and urllib.parse.urlparse(u).path.lower().endswith((".mp4",".webm",".ogv",".mov",".m4v"))]
                if not candidates:
                    continue
                rights = clean(source.get("rights"))
                out.append(item("dpla", clean(row.get("id")), title, candidates[0], obj if obj and not candidates[0] == obj else "", shown, clean(source.get("description")), clean(source.get("creator")), rights, "", "video"))
                if len(out) >= MAX_PER_SOURCE: return out
            time.sleep(0.5)
        return out
    return safe_call("dpla", run)

def twitch():
    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")
    if not client_id or not client_secret:
        METRICS["twitch"] = {"status":"skipped_missing_credentials","required":["TWITCH_CLIENT_ID","TWITCH_CLIENT_SECRET"]}
        print("SOURCE_SKIPPED twitch missing client credentials")
        return []
    def run():
        token_data = request_json("https://id.twitch.tv/oauth2/token", headers={}) if False else None
        body = urllib.parse.urlencode({"client_id":client_id,"client_secret":client_secret,"grant_type":"client_credentials"}).encode()
        req = urllib.request.Request("https://id.twitch.tv/oauth2/token", data=body, headers={"User-Agent":UA,"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            token_data = json.loads(response.read().decode("utf-8"))
        token = token_data.get("access_token")
        if not token: raise ValueError("Twitch OAuth não retornou access_token")
        headers = {"Client-Id":client_id,"Authorization":"Bearer "+token}
        out = []
        for query in ("science", "space", "education", "history", "music", "animation", "nature", "documentary"):
            data = request_json(qurl("https://api.twitch.tv/helix/search/videos", {"query":query,"first":100}), headers)
            for v in data.get("data", []):
                video_id = clean(v.get("id"))
                page_url = clean(v.get("url"))
                if not video_id or not page_url: continue
                thumb = clean(v.get("thumbnail_url")).replace("%{width}", "640").replace("%{height}", "360")
                out.append(item("twitch", video_id, clean(v.get("title")) or "Twitch video", page_url, thumb, page_url, clean(v.get("title")), clean(v.get("user_name")), "Twitch platform terms", "https://www.twitch.tv/p/legal/terms-of-service/", "", classify(query), "https://player.twitch.tv/?video=v"+video_id))
                if len(out) >= MAX_PER_SOURCE: return out
            time.sleep(0.5)
        return out
    return safe_call("twitch", run)

def gnews():
    # GNews indexes news articles, not a general video file catalog. Do not mislabel articles as videos.
    METRICS["gnews"] = {"status":"skipped_not_video_source","note":"GNews fornece artigos/notícias; não há arquivo de vídeo reproduzível garantido. Não inserir artigos no catálogo de vídeos."}
    print("SOURCE_SKIPPED gnews news articles are not playable video records")
    return []

def watchmod():
    # The API hostname, authentication method, and request schema must be confirmed before calling it.
    if not os.getenv("WATCHMOD_API_KEY"):
        METRICS["watchmod"] = {"status":"skipped_missing_credentials","required":"WATCHMOD_API_KEY"}
        print("SOURCE_SKIPPED watchmod missing WATCHMOD_API_KEY")
    else:
        METRICS["watchmod"] = {"status":"skipped_unverified_api_contract","note":"Secret existe, mas endpoint e esquema oficial precisam ser confirmados para não enviar a chave a um host incorreto."}
        print("SOURCE_SKIPPED watchmod API endpoint not verified; key was not transmitted")
    return []

def mit_ocw():
    METRICS["mit_ocw"] = {"status":"skipped_no_verified_video_api","note":"Nenhuma API pública geral de vídeo foi confirmada; não fazer scraping não autorizado."}
    print("SOURCE_SKIPPED mit_ocw no verified general video API; no scraping")
    return []

def dareful():
    METRICS["dareful"] = {"status":"skipped_no_verified_automated_api","note":"Não foi encontrada interface oficial de coleta automatizada neste módulo; não fazer scraping não autorizado."}
    print("SOURCE_SKIPPED dareful no verified automated API; no scraping")
    return []

def collect():
    all_items = []
    adapters = [
        ("pexels", pexels), ("pixabay", pixabay), ("nasa", nasa),
        ("wikimedia_commons", wikimedia), ("europeana", europeana),
        ("dvids", dvids), ("dpla", dpla), ("twitch", twitch), ("gnews", gnews), ("watchmod", watchmod), ("openverse", openverse),
        ("library_of_congress", library_of_congress),
        ("prelinger", internet_archive_prelinger), ("peertube", peertube),
        ("mit_ocw", mit_ocw), ("dareful", dareful),
    ]
    for name, adapter in adapters:
        try:
            got = adapter() or []
            all_items.extend(got)
            if name not in METRICS:
                METRICS[name] = {"status":"ok","found":len(got),"accepted":len(got)}
        except Exception as exc:
            METRICS[name] = {"status":"error","errors":1,"error":str(exc)[:220]}
            print("SOURCE_ERROR", name, type(exc).__name__, str(exc)[:180])
    print("MULTISOURCE_METRICS", json.dumps(METRICS, ensure_ascii=False, sort_keys=True))
    return all_items, METRICS
