import json, os, time, urllib.parse, urllib.request
from fontes_multiplas import collect as collect_external_sources
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "catalog.json"
DIR = ROOT / "catalog"
TARGET = int(os.getenv("TARGET_CANDIDATES", "2000"))
CHECKS = int(os.getenv("MAX_METADATA_CHECKS", "2000"))
TEXT_MODERATION_ENABLED = os.getenv("ENABLE_TEXT_MODERATION", "true").strip().lower() in ("1", "true", "yes", "on")
# Categorias públicas mantidas estáveis para não quebrar catalog/*.json nem o app.
# Cada consulta é ATÔMICA: um tema específico por busca, com sinônimos em inglês
# porque o Internet Archive indexa muitos registros nesse idioma.
# A coleta percorre as consultas até atingir a cota da categoria ou esgotar resultados.
CATS = [
 ("filmes","Filmes",[
  'mediatype:movies AND (title:adventure OR subject:adventure OR subject:exploration)',
  'mediatype:movies AND (title:action OR subject:action OR subject:superhero OR subject:heroes)',
  'mediatype:movies AND (title:romance OR subject:romance OR subject:romantic)',
  'mediatype:movies AND (title:drama OR subject:drama OR subject:family drama)',
  'mediatype:movies AND (title:comedy OR subject:comedy OR subject:comedies OR subject:"romantic comedy")',
  'mediatype:movies AND (title:mystery OR subject:mystery OR subject:detective OR subject:investigation)',
  'mediatype:movies AND (subject:suspense OR subject:thriller) NOT (subject:horror OR subject:terror)',
  'mediatype:movies AND (subject:musical OR subject:musicals OR subject:operetta)',
  'mediatype:movies AND (subject:"international cinema" OR subject:"world cinema" OR subject:foreign)',
  'mediatype:movies AND (subject:"classic film" OR subject:"family film" OR subject:"classic cinema")',
  'mediatype:movies AND (title:film OR subject:cinema) AND (subject:adventure OR subject:comedy OR subject:drama) NOT (subject:horror OR subject:western)'
 ]),
 ("desenhos","Desenhos",[
  'mediatype:movies AND (subject:cartoons OR subject:"classic cartoons" OR subject:"animated shorts")',
  'mediatype:movies AND (subject:superheroes OR subject:"super heroes" OR title:superman OR title:batman)',
  'mediatype:movies AND (subject:"animated adventure" OR subject:"animated action" OR subject:animation)',
  'mediatype:movies AND (subject:"cartoon comedy" OR subject:"comedy cartoons" OR subject:"classic animation")',
  'mediatype:movies AND (subject:"educational cartoons" OR subject:"preschool" OR subject:"children animation")',
  'mediatype:movies AND (subject:"animal cartoons" OR subject:"children stories" OR subject:"fairy tales")',
  'mediatype:movies AND (subject:"science animation" OR subject:"space animation" OR subject:"educational animation")',
  'mediatype:movies AND (subject:"anime adventure" OR subject:"anime comedy" OR subject:"Japanese animation")',
  'mediatype:movies AND (subject:animation OR subject:cartoons) NOT (subject:hentai OR subject:adult OR subject:erotic)'
 ]),
 ("series","Séries",[
  'mediatype:movies AND (subject:"adventure series" OR subject:"action series" OR subject:serials) NOT subject:episode',
  'mediatype:movies AND (subject:"comedy series" OR subject:"television comedy" OR subject:sitcom) NOT subject:episode',
  'mediatype:movies AND (subject:"drama series" OR subject:"television drama") NOT subject:episode',
  'mediatype:movies AND (subject:"mystery series" OR subject:detective OR subject:investigation) NOT subject:episode',
  'mediatype:movies AND (subject:"science fiction series" OR subject:"sci-fi" OR subject:"space series") NOT subject:episode',
  'mediatype:movies AND (subject:"educational television" OR subject:"educational program" OR subject:"instructional television")',
  'mediatype:movies AND (subject:"short films" OR subject:"television shorts" OR subject:"animated shorts")'
 ]),
 ("documentarios","Documentários",[
  'mediatype:movies AND (subject:documentary OR subject:documentaries) AND (subject:education OR subject:educational)',
  'mediatype:movies AND (subject:documentary OR subject:documentaries) AND (subject:science OR subject:scientific)',
  'mediatype:movies AND (subject:documentary OR subject:documentaries) AND (subject:nature OR subject:animals OR subject:ocean)',
  'mediatype:movies AND (subject:documentary OR subject:documentaries) AND (subject:history OR subject:historical)',
  'mediatype:movies AND (subject:documentary OR subject:documentaries) AND (subject:archaeology OR subject:civilization)',
  'mediatype:movies AND (subject:documentary OR subject:documentaries) AND (subject:biography OR subject:biographies)',
  'mediatype:movies AND (subject:documentary OR subject:documentaries) AND (subject:geography OR subject:culture OR subject:people)'
 ]),
 ("comedia","Comédia",[
  'mediatype:movies AND (subject:comedy OR subject:comedies OR subject:humor) NOT (subject:horror OR subject:adult)',
  'mediatype:movies AND (subject:"romantic comedy" OR subject:"comedy film" OR subject:"family comedy")'
 ]),
 ("historia","História",[
  'mediatype:movies AND (subject:"ancient history" OR subject:civilization OR subject:civilizations)',
  'mediatype:movies AND (subject:Egypt OR subject:Rome OR subject:Greece) AND (subject:history OR subject:historical)',
  'mediatype:movies AND (subject:Brazil OR subject:"Latin America") AND (subject:history OR subject:historical)',
  'mediatype:movies AND (subject:"world history" OR subject:historical OR subject:history)',
  'mediatype:movies AND (subject:archaeology OR subject:archaeological OR subject:discoveries)',
  'mediatype:movies AND (subject:biography OR subject:biographies OR subject:biographical)',
  'mediatype:movies AND (subject:museums OR subject:heritage OR subject:preservation)',
  'mediatype:movies AND (subject:geography OR subject:ethnography OR subject:cultures)',
  'mediatype:movies AND (subject:aviation OR subject:aircraft OR subject:transportation history)'
 ]),
 ("ciencia","Ciência e espaço",[
  'mediatype:movies AND (title:NASA OR subject:NASA OR subject:"space missions")',
  'mediatype:movies AND (subject:astronomy OR subject:planets OR subject:astrophysics)',
  'mediatype:movies AND (subject:"solar system" OR subject:planetary OR subject:solar)',
  'mediatype:movies AND (subject:stars OR subject:galaxies OR subject:universe OR subject:cosmology)',
  'mediatype:movies AND (subject:Moon OR subject:Mars OR subject:"lunar exploration")',
  'mediatype:movies AND (subject:rockets OR subject:"space station" OR subject:spaceflight)',
  'mediatype:movies AND (subject:physics OR subject:technology OR subject:engineering)',
  'mediatype:movies AND (subject:inventions OR subject:scientific discoveries OR subject:innovation)',
  'mediatype:movies AND (subject:nature OR subject:ocean OR subject:animals OR subject:wildlife)',
  'mediatype:movies AND (subject:science OR subject:scientific) AND (subject:education OR subject:educational)'
 ]),
 ("musica","Música e shows",[
  'mediatype:movies AND (subject:music OR subject:musical performance OR subject:concerts)',
  'mediatype:movies AND (subject:live music OR subject:live concert OR subject:orchestra)',
  'mediatype:movies AND (subject:performing arts OR subject:theater OR subject:theatre)',
  'mediatype:movies AND (subject:classical music OR subject:opera OR subject:choir)'
 ])
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
    "erotik", "porno film",
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
    # Chave temporária para diagnóstico do catálogo; não representa certificação familiar.
    if not TEXT_MODERATION_ENABLED:
        return True
    # Moderação por contexto: título/arquivo/coleção têm regra forte;
    # descrição e metadados gerais só bloqueiam expressões explicitamente perigosas.
    # Isso evita rejeitar obras legítimas porque a descrição cita um tema incidentalmente.
    title = normalized_text(item.get("title", ""))
    identifier = normalized_text(item.get("identifier", ""))
    collection_value = item.get("collection", [])
    collection_values = collection_value if isinstance(collection_value, list) else [collection_value]
    collections = [normalized_text(v) for v in collection_values if normalized_text(v)]
    filenames = [
        normalized_text(f.get("name", ""))
        for f in item.get("files", [])
        if isinstance(f, dict) and f.get("name")
    ]

    # Bloqueio forte em título e nome real do arquivo reproduzido.
    high_risk = " ".join([title, " ".join(filenames)])
    if any(p.search(high_risk) for p in BLOCKED_PATTERNS + BLOCKED_FIELD_PATTERNS):
        return False

    # Coleção é um sinal forte apenas quando corresponde a uma coleção adulta conhecida
    # ou contém uma expressão explícita, não por conter uma palavra genérica isolada.
    if any(v.strip() in BLOCKED_COLLECTIONS for v in collections):
        return False
    if any(p.search(" ".join(collections)) for p in BLOCKED_FIELD_PATTERNS):
        return False

    # O identificador técnico não é texto editorial e não deve ser usado para
    # rejeitar conteúdo; só o verificamos contra sinais explícitos de alto risco.
    if any(p.search(identifier) for p in BLOCKED_FIELD_PATTERNS):
        return False

    # Campos descritivos podem citar palavras ambíguas em contexto histórico,
    # educativo ou crítico. Neles, somente frases explícitas/contextuais bloqueiam.
    descriptive_fields = [
        item.get("description", ""), item.get("creator", ""),
        item.get("subject", ""), item.get("mediatype", ""),
        item.get("format", ""), item.get("licenseurl", ""),
        item.get("license", ""),
    ]
    descriptive_text = normalized_text(" ".join(text(v) for v in descriptive_fields))
    return not any(p.search(descriptive_text) for p in BLOCKED_FIELD_PATTERNS)

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
    for key,title,queries in CATS:
        added=0
        # Busca atômica: cada subgênero tem sua consulta e diagnóstico próprios.
        # O orçamento é compartilhado pela categoria para evitar que um único
        # termo popular consuma toda a cota. O conjunto seen evita duplicados.
        for query in queries:
            if added>=per: break
            page=1
            while added<per:
                # Sempre pedir até 100 resultados para detectar o fim real da paginação.
                rows=100
                payload=search(query,page,rows)
                if payload is None:
                    print("SEARCH_ERROR",key,"query=",query,"page=",page)
                    break
                docs=(payload or {}).get("response",{}).get("docs",[])
                if not docs: break
                accepted_before=len(candidates)
                for d in docs:
                    ident=text(d.get("identifier")); name=text(d.get("title"))
                    if not ident or not name or ident in seen: continue
                    if not is_family_safe({"identifier":ident,"title":name,"description":text(d.get("description")),"creator":text(d.get("creator")),"subject":text(d.get("subject")),"collection":text(d.get("collection"))}):
                        print("BLOCKED unsafe metadata:",ident,"category=",key)
                        continue
                    seen.add(ident); added+=1
                    candidates.append({"identifier":ident,"title":name,"description":text(d.get("description"))[:1200],"year":text(d.get("year")),"creator":text(d.get("creator")),"subject":text(d.get("subject")),"collection":text(d.get("collection")),"mediatype":text(d.get("mediatype")),"license":text(d.get("licenseurl")),"detailsUrl":"https://archive.org/details/"+ident,"thumbnail":"https://archive.org/services/img/"+ident,"category":key,"files":[],"playbackUrl":None})
                    if added>=per: break
                print("QUERY_RESULT",key,"page=",page,"received=",len(docs),"new_candidates=",len(candidates)-accepted_before,"category_total=",added)
                if len(docs)<rows: break
                page+=1; time.sleep(.15)
        print("CATEGORY_CANDIDATES",key,added,"quota=",per,"atomic_queries=",len(queries))
    print("Unique candidates:",len(candidates),"target:",TARGET)
    checked=0
    for item in candidates:
        if item["identifier"] in old or checked>=CHECKS: continue
        checked+=1
        valid=validate(item)
        if valid: old[valid["identifier"]]=valid
        time.sleep(.2)
    # Fontes adicionais independentes. A falha de uma fonte não interrompe as outras.
    external_items, source_metrics = collect_external_sources()
    external_added = 0
    # Deduplicação entre fontes por identificador e URL canônica do arquivo.
    known_urls = set()
    for existing in old.values():
        for file_record in existing.get("files", []) if isinstance(existing.get("files"), list) else []:
            url = text(file_record.get("url") if isinstance(file_record, dict) else "")
            parsed_url = urllib.parse.urlparse(url)
            if parsed_url.scheme == "https" and parsed_url.netloc:
                known_urls.add((parsed_url.netloc.lower(), parsed_url.path.rstrip("/")))
    for external in external_items:
        ident = text(external.get("identifier"))
        if not ident or ident in old:
            continue
        if not external.get("title") or not external.get("playbackUrl") or not external.get("files"):
            print("SOURCE_REJECTED invalid normalized record:", ident)
            continue
        if not is_family_safe(external):
            print("SOURCE_REJECTED unsafe metadata:", ident, "source=", external.get("source"))
            continue
        # URL de reprodução precisa ser HTTPS e apontar para uma mídia reconhecível.
        playback = urllib.parse.urlparse(text(external.get("playbackUrl")))
        if playback.scheme != "https" or not playback.hostname:
            print("SOURCE_REJECTED invalid playback URL:", ident)
            continue
        canonical = (playback.netloc.lower(), playback.path.rstrip("/"))
        if canonical in known_urls:
            print("SOURCE_DUPLICATE canonical URL:", ident)
            continue
        known_urls.add(canonical)
        external["validatedAt"] = datetime.now(timezone.utc).isoformat()
        old[ident] = external
        external_added += 1
    print("MULTISOURCE_ACCEPTED_AFTER_TEXT_MODERATION", external_added)
    groups={key:[] for key,_,_ in CATS}
    candidate_ids={x["identifier"]:x["category"] for x in candidates}
    for ident,item in old.items():
        item["category"]=candidate_ids.get(ident,item.get("category","filmes"))
        if item["category"] not in groups: item["category"]="filmes"
        # Política por item: fonte confiável recebe filtros textuais; fontes
        # abertas/UGC e Internet Archive também exigem análise visual NSFWJS.
        source = text(item.get("source")).strip().lower()
        if not source:
            source = "internet-archive"
            item["source"] = source
        # Apenas fontes oficiais explicitamente allowlistadas podem dispensar análise visual.
        trusted_text_only_sources = {"nasa", "dvids", "europeana"}
        item["moderationPolicy"] = "text+trusted-source" if source in trusted_text_only_sources else "text+visual"
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
    catalog={"schemaVersion":1,"source":"Internet Archive","updatedAt":now,"candidateTarget":TARGET,"candidatesCollectedThisRun":len(candidates),"metadataChecksThisRun":checked,"multiSourceAcceptedThisRun":external_added,"sourceMetrics":source_metrics,"count":len(items),"items":items,"categories":[{"key":k,"title":t,"count":len(groups[k]),"path":"catalog/"+k+".json"} for k,t,_ in CATS],"notes":["Items are included only when a video file is found.","Check rights and licenses per item; an Archive listing is not automatically public domain.","Playback support depends on the file format and browser."]}
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
