"""
Využití předplatného Claude — totéž, co ukazuje `/usage` v Claude Code:
kolik je vyčerpáno z limitu na 5 hodin, z týdenního limitu a kdy se který
obnoví.

Čísla dává Anthropic, ne přepisy sezení (ty počítá hub/stats.py v dolarech
a tokenech). Tahle čísla jsou procenta *skutečného* limitu předplatného.

Dvě cesty, od bohatší k jednodušší:

1. `GET /api/oauth/usage` — to samé, z čeho čte `/usage`. Chce přihlášení se
   scope `user:profile` (tedy to z počítače, `~/.claude/.credentials.json`).
2. Když ten scope chybí (token z `claude setup-token`, který je v prostoru na
   serveru — jen `user:inference`), jde to z hlaviček odpovědi na jednu
   minimální zprávu (`anthropic-ratelimit-unified-*`). Stojí to zlomek centu
   a čte se jen jednou za pár minut.

Token se čte jen pro tuhle jednu otázku, nikam se neposílá ani neukládá a
neobnovuje se (obnovení by otočilo obnovovací token a odhlásilo by Claude
Code).
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.anthropic.com"
BETA = "oauth-2025-04-20"
TTL = 90            # tolik vteřin se odpověď drží (stránka se může ptát častěji)
TIMEOUT = 15

_lock = threading.Lock()
_cache = {"t": 0.0, "key": "", "data": None}


# ── token ────────────────────────────────────────────────────────────────────
def _config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def own_token():
    """Přihlášení tohohle člověka: prostředí (prostor na serveru), pak soubor
    s přihlášením (Linux, Windows) nebo klíčenka (macOS). Prázdné = není."""
    tok = (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip()
    if tok:
        return tok
    data = None
    try:
        with open(os.path.join(_config_dir(), ".credentials.json"), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = None
    if data is None and sys.platform == "darwin":
        try:
            out = subprocess.run(["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                                 capture_output=True, text=True, timeout=5)
            data = json.loads(out.stdout) if out.returncode == 0 else None
        except (OSError, ValueError, subprocess.SubprocessError):
            data = None
    oauth = (data or {}).get("claudeAiOauth") or {}
    return str(oauth.get("accessToken") or "").strip()


# ── dotaz ────────────────────────────────────────────────────────────────────
def _iso(epoch):
    try:
        return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _okno(src):
    """{"pct", "resets"} z okna limitu, nebo None."""
    if not isinstance(src, dict) or src.get("utilization") is None:
        return None
    try:
        pct = float(src["utilization"])
    except (TypeError, ValueError):
        return None
    return {"pct": round(pct, 1), "resets": src.get("resets_at")}


def _z_usage(raw):
    out = {"session": _okno(raw.get("five_hour")), "week": _okno(raw.get("seven_day")),
           "week_sonnet": _okno(raw.get("seven_day_sonnet")), "week_opus": _okno(raw.get("seven_day_opus")),
           "zdroj": "usage"}
    extra = raw.get("extra_usage")
    if isinstance(extra, dict) and extra.get("is_enabled"):
        out["extra"] = {"used": extra.get("used_credits"), "limit": extra.get("monthly_limit"),
                        "pct": extra.get("utilization"), "mena": extra.get("currency"),
                        "dec": extra.get("decimal_places") or 2}
    return out


def _z_hlavicek(headers):
    h = {k.lower(): v for k, v in headers.items()}

    def pct(key):
        try:
            return round(float(h[key]) * 100, 1)
        except (KeyError, TypeError, ValueError):
            return None
    out = {"zdroj": "hlavicky", "week_sonnet": None, "week_opus": None}
    for nazev, kod in (("session", "5h"), ("week", "7d")):
        p = pct("anthropic-ratelimit-unified-%s-utilization" % kod)
        out[nazev] = None if p is None else {"pct": p, "resets": _iso(h.get("anthropic-ratelimit-unified-%s-reset" % kod))}
    return out


def _req(path, token, body=None):
    headers = {"Authorization": "Bearer " + token, "anthropic-beta": BETA,
               "anthropic-version": "2023-06-01", "User-Agent": "claude-hub-usage"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
    return urllib.request.Request(API + path, data=data, headers=headers, method="POST" if body is not None else "GET")


def fetch(token):
    """Využití pro daný token. {"ok": True, "session", "week", …} nebo {"ok": False, "chyba", "druh"}."""
    if not token:
        return {"ok": False, "druh": "bez-prihlaseni",
                "chyba": "Claude tu není přihlášený, takže nemám čí limit ukázat."}
    try:
        with urllib.request.urlopen(_req("/api/oauth/usage", token), timeout=TIMEOUT) as r:
            out = _z_usage(json.loads(r.read().decode("utf-8")))
            if out["session"] or out["week"]:
                out["ok"] = True
                return out
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return {"ok": False, "druh": "vyprselo",
                    "chyba": "Přihlášení vypršelo. Otevři Claude Code, obnoví se samo, a zkus to znovu."}
        # 403 (token bez scope user:profile) a ostatní: zkusit druhou cestu.
    except (OSError, ValueError):
        pass
    try:
        body = {"model": "claude-haiku-4-5", "max_tokens": 1,
                "system": "You are Claude Code, Anthropic's official CLI for Claude.",
                "messages": [{"role": "user", "content": "hi"}]}
        with urllib.request.urlopen(_req("/v1/messages", token, body), timeout=TIMEOUT) as r:
            out = _z_hlavicek(dict(r.headers.items()))
    except urllib.error.HTTPError as exc:
        if exc.code == 429 and exc.headers:
            out = _z_hlavicek(dict(exc.headers.items()))     # vyčerpáno: hlavičky přijdou i tak
        elif exc.code in (401, 403):
            return {"ok": False, "druh": "vyprselo", "chyba": "Přihlášení Clauda je neplatné nebo vypršelo."}
        else:
            return {"ok": False, "druh": "chyba", "chyba": "Anthropic teď neodpovídá (HTTP %d)." % exc.code}
    except (OSError, ValueError):
        return {"ok": False, "druh": "sit", "chyba": "Nejde se spojit s Anthropic, zkus to za chvíli."}
    if not (out.get("session") or out.get("week")):
        return {"ok": False, "druh": "chyba", "chyba": "Anthropic limit tomuhle přihlášení neukázal."}
    out["ok"] = True
    return out


def own(refresh=False):
    """Využití přihlášení, pod kterým hub běží. Drží se TTL vteřin."""
    token = own_token()
    key = token[-12:] if token else ""
    with _lock:
        if (not refresh and _cache["data"] is not None and _cache["key"] == key
                and time.time() - _cache["t"] < TTL):
            return _cache["data"]
    data = fetch(token)
    data["cas"] = int(time.time())
    with _lock:
        _cache.update({"t": time.time(), "key": key, "data": data})
    return data
