import json, os, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "catalog.json"
DIR = ROOT / "catalog"
TARGET = int(os.getenv("TARGET_CANDIDATES", "2000"))
CHECKS = int(os.getenv("MAX_METADATA_CHECKS", "2000"))
CATS = [
 ("filmes","Filmes",'mediatype:movies AND (subject:film OR subject:cinema)'),
 ("desenhos","Desenhos",'mediatype:movies AND (subject:animation OR subject:cartoons)'),
 ("series","Séries (filmes completos)",'mediatype:movies AND (subject:television OR subject:tv series OR subject:serials) NOT subject:episode'),
 ("documentarios","Documentários",'mediatype:movies AND (subject:documentary OR subject:documentaries)'),
 ("comedia","Comédia",'mediatype:movies AND (subject:comedy OR subject:humor)'),
 ("historia","História",'mediatype:movies AND (subject:history OR subject:historical)'),
 ("ciencia","Ciência e espaço",'mediatype:movies AND (subject:science OR subject:space OR subject:astronomy OR subject:nasa)'),
 ("musica","Música e shows",'mediatype:movies AND (subject:music OR subject:concerts OR subject:performance)')
]
VIDEO_EXT = (".mp4",".m4v",".webm",".ogv",".mov",".mpeg",".mpg",".avi")

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent":"PLAYERS-catalog/1.0","Accept":"application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print("Request error:", e)
            time.sleep(2)
    return None

def text(v):
    return ", ".join(map(str,v)) if isinstance(v,list) else str(v or "").strip()

# Moderacao familiar multilíngue baseada em metadados.
# Bloqueia sinais explícitos; não substitui análise visual do vídeo.
import re
import unicodedata

BLOCKED_TERMS = [
    # Sexual explícito / pornografia
    "porn", "pornography", "pornographic", "porno", "pornografia", "pornografico",
    "pornografica", "pornográfico", "pornográfica", "xxx", "hentai", "erotic",
    "erotica", "erotika", "erotico", "erotica", "erótico", "erótica",
    "sex tape", "sex film", "sex video", "sex clip", "sexually explicit",
    "explicit sex", "sexual intercourse", "sexual content", "adult video",
    "adult film", "adult movie", "adult entertainment", "hardcore",
    "softcore", "striptease", "stripping", "prostitution", "escort",
    "nude", "nudity", "nudes", "naked", "topless", "bare breasts",
    "desnudo", "desnuda", "desnudos", "desnudez", "sexo explicito",
    "sexo explícito", "filme adulto", "filme erotico", "filme erótico",
    "conteudo sexual", "conteúdo sexual", "conteudo adulto", "conteúdo adulto",
    "sexo", "sexual", "seksual", "sexuell", "erotik", "porno film",
    "pornofilm", "pornovideo", "sexfilm", "sexvideo", "sexclip",
    "film erotique", "film pornographique", "vidéo pornographique", "glissements progressifs du plaisir", "adult only", "adults only", "uncensored", "uncut erotic", "erotic drama", "erotic thriller", "sexploitation", "nudist film", "nudism", "naturist film", "naturism",
    "pelicula pornografica", "película pornográfica", "contenido sexual",
    "contenido para adultos", "contenido adulto", "sexo amateur",
    "amateur porn", "onlyfans", "fetish", "bdsm", "bondage", "incest",
    "rape", "sexual assault", "sexual abuse", "child sexual abuse",
    "violacao sexual", "violação sexual", "abuso sexual", "estupro",
    "порно", "порнография", "эротика", "секс", "色情", "成人视频",
    "猥褻", "成人向け", "ポルノ", "セックス", "섹스", "포르노",
    # Violência gráfica / extrema
    "gore", "snuff film", "snuff movie", "graphic violence", "torture",
    "beheading", "decapitation", "dismemberment", "execution video",
    "real murder", "real killing", "brutal killing", "extreme violence",
    "violent pornography", "murder footage", "massacre footage",
    "tortura", "decapitacao", "decapitação", "esquartejamento",
    "violencia grafica", "violência gráfica", "execucao real", "execução real",
    "video de execução", "vídeo de execução", "film de torture", "eyewitness news", "graphic footage", "terror attack footage",
    "guerra gore", "暴力描写", "拷問", "斬首", "残虐",
    # Palavrões comuns em vários idiomas (termos isolados)
    "fuck", "fucking", "motherfucker", "shit", "bullshit", "bitch",
    "cunt", "cock", "dick", "pussy", "dildo", "blowjob", "handjob",
    "asshole", "fucker", "merda", "porra", "caralho", "buceta", "puta",
    "putaria", "foder", "fodendo", "foda-se", "fodase", "cacete",
    "mierda", "joder", "jodido", "coño", "cojones", "cabron", "cabrón",
    "puta madre", "putain", "merde", "connard", "salope",
    "scheisse", "scheiße", "ficken", "arschloch", "hure",
    "kurwa", "chuj", "blyat", "блядь", "сука", "хуй", "пизда",
]

def normalized_text(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("_", " ").replace("-", " ")
    return re.sub(r"[^a-z0-9\s\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", " ", value)

BLOCKED_PATTERNS = [
    re.compile(r"(?<![a-z0-9])" + re.escape(normalized_text(term)).replace(r"\ ", r"\s+") + r"(?![a-z0-9])")
    for term in BLOCKED_TERMS
]

# Sinais fortes de acervos adultos; são avaliados separadamente dos termos genéricos.
BLOCKED_COLLECTIONS = {
    "adult", "adults", "adult content", "adult movies", "adult videos",
    "erotic", "erotica", "porn", "pornography", "xxx", "hentai",
    "sex films", "sex videos", "nudist", "nudism", "sexploitation"
}
BLOCKED_FIELD_TERMS = [
    "adult category", "adult collection", "erotic collection", "porn collection",
    "pornographic film", "erotic film", "erotic cinema", "explicit scenes",
    "full frontal nudity", "full frontal", "graphic sexual content",
    "sexualized", "sexually explicit", "sexual stimulation", "sexual fantasy",
    "adult entertainment", "adult material", "18 plus", "18+", "rated x",
    "rating x", "xxx rated", "uncensored adult", "erotic french film",
    "film érotique", "film erotique", "glissements progressifs du plaisir",
    "erwachsenenfilm", "film per adulti", "película erótica", "pelicula erotica",
    "contenido explícito", "contenido explicito", "material pornográfico",
    "material pornografico", "conteúdo explícito", "conteudo explicito",
    "vídeo erótico", "video erotico", "filme de sexo", "filme sexual"
]
BLOCKED_FIELD_PATTERNS = [
    re.compile(r"(?<![a-z0-9])" + re.escape(normalized_text(term)).replace(r"\ ", r"\s+") + r"(?![a-z0-9])")
    for term in BLOCKED_FIELD_TERMS
]

def is_family_safe(item):
    # Examina metadados textuais e nomes dos arquivos; não faz análise visual.
    fields = [
        item.get("identifier", ""), item.get("title", ""),
        item.get("description", ""), item.get("creator", ""),
        item.get("subject", ""), item.get("collection", ""),
        item.get("mediatype", ""), item.get("format", ""),
        item.get("licenseurl", ""), item.get("license", ""),
        " ".join(text(f.get("name", "")) + " " + text(f.get("format", ""))
                 for f in item.get("files", []) if isinstance(f, dict))
    ]
    field_map = {k: normalized_text(item.get(k, "")) for k in ("title", "identifier", "subject", "collection")}
    collection_values = [normalized_text(v) for v in (
        item.get("collection", []) if isinstance(item.get("collection"), list)
        else [item.get("collection", "")]
    )]
    if any(v.strip() in BLOCKED_COLLECTIONS for v in collection_values if v.strip()):
        return False
    # Título, ID e arquivo recebem a regra de segurança mais estrita.
    high_risk = " ".join([
        field_map["title"], field_map["identifier"],
        " ".join(text(f.get("name", "")) for f in item.get("files", []) if isinstance(f, dict))
    ])
    if any(p.search(high_risk) for p in BLOCKED_PATTERNS + BLOCKED_FIELD_PATTERNS):
        return False
    all_text = normalized_text(" ".join(str(v or "") for v in fields))
    return not any(p.search(all_text) for p in BLOCKED_PATTERNS + BLOCKED_FIELD_PATTERNS)

def search(query, page, rows):
    params = [("q",query),("fl[]","identifier"),("fl[]","title"),("fl[]","description"),("fl[]","year"),("fl[]","creator"),("fl[]","licenseurl"),("fl[]","subject"),("fl[]","collection"),("fl[]","mediatype"),("fl[]","format"),("rows",str(rows)),("page",str(page)),("output","json"),("sort[]","downloads desc")]
    return get_json("https://archive.org/advancedsearch.php?"+urllib.parse.urlencode(params))

def validate(item):
    meta = get_json("https://archive.org/metadata/"+urllib.parse.quote(item["identifier"],safe=""))
    if not meta or not isinstance(meta.get("files"),list): return None
    metadata = meta.get("metadata") or {}
    enriched = dict(item)
    for field in ("title", "description", "creator", "subject", "collection", "mediatype", "licenseurl", "format"):
        if metadata.get(field):
            enriched[field] = metadata.get(field)
    if not is_family_safe(enriched):
        print("BLOCKED unsafe full metadata:", item.get("identifier"))
        return None
    files=[]
    for f in meta["files"]:
        name=text(f.get("name"))
        if name.lower().endswith(VIDEO_EXT) and not f.get("private") and is_family_safe({**enriched, "files":[f]}):
            files.append({"name":name,"format":text(f.get("format")),"size":int(f.get("size") or 0),"url":"https://archive.org/download/"+urllib.parse.quote(item["identifier"],safe="")+"/"+urllib.parse.quote(name,safe="/")})
    if not files: return None
    item.update({k: text(enriched.get(k)) for k in ("title","description","creator","subject","collection","mediatype","licenseurl","format") if enriched.get(k)})
    item["files"]=files
    if not is_family_safe(item): return None
    files.sort(key=lambda x:(not x["name"].lower().endswith((".mp4",".webm",".m4v")),-x["size"]))
    item["files"]=files[:8]
    item["playbackUrl"]=files[0]["url"]
    item["validatedAt"]=datetime.now(timezone.utc).isoformat()
    return item

def main():
    DIR.mkdir(exist_ok=True)
    old={}
    try:
        previous=json.loads(OUT.read_text(encoding="utf-8"))
        for x in previous.get("items",[]):
            if x.get("identifier") and x.get("playbackUrl") and is_family_safe(x): old[x["identifier"]]=x
    except Exception: pass
    for key,_,_ in CATS:
        try:
            previous=json.loads((DIR/(key+".json")).read_text(encoding="utf-8"))
            for x in previous.get("items",[]):
                if x.get("identifier") and x.get("playbackUrl") and is_family_safe(x): old.setdefault(x["identifier"],x)
        except Exception: pass
    per=max(1,(TARGET+len(CATS)-1)//len(CATS))
    candidates=[]; seen=set()
    for key,title,query in CATS:
        page=1; added=0
        while added<per:
            payload=search(query,page,min(200,per-added))
            docs=(payload or {}).get("response",{}).get("docs",[])
            if not docs: break
            for d in docs:
                ident=text(d.get("identifier")); name=text(d.get("title"))
                if not ident or not name or ident in seen: continue
                if not is_family_safe({"identifier":ident,"title":name,"description":text(d.get("description")),"creator":text(d.get("creator"))}):
                    print("BLOCKED unsafe metadata:", ident)
                    continue
                seen.add(ident); added+=1
                candidates.append({"identifier":ident,"title":name,"description":text(d.get("description"))[:1200],"year":text(d.get("year")),"creator":text(d.get("creator")),"subject":text(d.get("subject")),"collection":text(d.get("collection")),"mediatype":text(d.get("mediatype")),"license":text(d.get("licenseurl")),"detailsUrl":"https://archive.org/details/"+ident,"thumbnail":"https://archive.org/services/img/"+ident,"category":key,"files":[],"playbackUrl":None})
                if added>=per: break
            page+=1; time.sleep(.15)
        print(key, "candidates:",added)
    print("Unique candidates:",len(candidates),"target:",TARGET)
    checked=0
    for item in candidates:
        if item["identifier"] in old or checked>=CHECKS: continue
        checked+=1
        valid=validate(item)
        if valid: old[valid["identifier"]]=valid
        time.sleep(.2)
    groups={key:[] for key,_,_ in CATS}
    candidate_ids={x["identifier"]:x["category"] for x in candidates}
    for ident,item in old.items():
        item["category"]=candidate_ids.get(ident,item.get("category","filmes"))
        if item["category"] not in groups: item["category"]="filmes"
        groups[item["category"]].append(item)
    now=datetime.now(timezone.utc).isoformat()
    items=sorted([x for group in groups.values() for x in group],key=lambda x:(x.get("category",""),x.get("title","").casefold()))
    # Fail closed BEFORE touching any published catalog file. Actions will restore
    # the previous catalog if collection or moderation fails.
    if not items:
        raise RuntimeError(
            "Coleta resultou em zero itens reproduzíveis. Catálogo anterior preservado; "
            "verifique conectividade, filtros e respostas da API do Internet Archive."
        )
    print("Resumo por categoria:", {key: len(value) for key, value in groups.items()})
    print("Candidatos coletados:", len(candidates), "| verificações de metadados:", checked, "| itens finais:", len(items))
    catalog={"schemaVersion":1,"source":"Internet Archive","updatedAt":now,"candidateTarget":TARGET,"candidatesCollectedThisRun":len(candidates),"metadataChecksThisRun":checked,"count":len(items),"items":items,"categories":[{"key":k,"title":t,"count":len(groups[k]),"path":"catalog/"+k+".json"} for k,t,_ in CATS],"notes":["Items are included only when a video file is found.","Check rights and licenses per item; an Archive listing is not automatically public domain.","Playback support depends on the file format and browser."]}
    # Write the consolidated catalog atomically first; the workflow backup restores
    # both it and category files if any later validation/moderation step fails.
    tmp=OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(OUT)
    for key,title,_ in CATS:
        category_items=sorted(groups[key],key=lambda x:x.get("title","").casefold())
        category_tmp=DIR/(key+".json.tmp")
        category_tmp.write_text(json.dumps({"category":key,"title":title,"updatedAt":now,"count":len(category_items),"items":category_items},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        category_tmp.replace(DIR/(key+".json"))
    print("Saved",len(items),"validated items; metadata checks:",checked)

if __name__=="__main__": main()
