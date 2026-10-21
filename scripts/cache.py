import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CACHE_TTL_SECONDS = int(os.getenv("API_CACHE_TTL_SECONDS", str(5 * 24 * 60 * 60)))
CACHE_DIR = Path(os.getenv("API_CACHE_DIR", ".cache/api"))
SENSITIVE_QUERY_KEYS = {"key", "api_key", "apikey", "wskey", "client_secret", "access_token", "token"}


def _safe_cache_url(url):
    parts = urlsplit(url)
    query = [(key, "REDACTED" if key.lower() in SENSITIVE_QUERY_KEYS else value) for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), ""))


def _path(url):
    digest = hashlib.sha256(_safe_cache_url(url).encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def load(url):
    path = _path(url)
    try:
        if time.time() - path.stat().st_mtime > CACHE_TTL_SECONDS:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None


def save(url, payload):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(url)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def clear_expired():
    if not CACHE_DIR.exists():
        return
    cutoff = time.time() - CACHE_TTL_SECONDS
    for path in CACHE_DIR.glob("*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass
