from __future__ import annotations
import sys, json, requests, os

try:
    from tools._dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

BASE = (
    os.getenv("CAPITAL_API_BASE")
    or os.getenv("CAPITAL_BASE_URL")
    or "https://demo-api-capital.backend-capital.com"
).rstrip("/")
API = BASE + "/api/v1"


def _headers(extra=None):
    h = {
        "X-CAP-API-KEY": os.getenv("CAPITAL_API_KEY") or os.getenv("CAPITAL_KEY", ""),
        "Accept": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def login():
    r = requests.post(
        API + "/session",
        headers=_headers(),
        json={
            "identifier": os.getenv("CAPITAL_USERNAME")
            or os.getenv("CAPITAL_IDENTIFIER"),
            "password": os.getenv("CAPITAL_PASSWORD"),
            "encryptedPassword": False,
        },
        timeout=30,
    )
    r.raise_for_status()
    return {
        "CST": r.headers.get("CST", ""),
        "X-SECURITY-TOKEN": r.headers.get("X-SECURITY-TOKEN", ""),
    }


def search(tok, q):
    r = requests.get(
        API + "/markets",
        params={"search": q},
        headers={**_headers(), **tok},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("markets") or []


def details(tok, epic):
    r = requests.get(
        API + f"/markets/{epic}",
        headers={**_headers({"Version": "3"}), **tok},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m tools.market_info <SYMBOL or EPIC>")
        sys.exit(1)
    tok = login()
    q = sys.argv[1]
    hits = search(tok, q)
    if not hits:
        print(json.dumps({"ok": False, "error": "no_results"}))
        sys.exit(0)
    best = hits[0]
    epic = best.get("epic")
    md = details(tok, epic)
    print(
        json.dumps(
            {"ok": True, "epic": epic, "hit": best, "market_details": md},
            ensure_ascii=False,
            indent=2,
        )
    )
