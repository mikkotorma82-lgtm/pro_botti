from __future__ import annotations
import os, json, requests
from dataclasses import dataclass
from typing import Optional, List, Dict
from tools._dotenv import load_dotenv

load_dotenv()

DEF_TIMEOUT = 30


@dataclass
class Tokens:
    cst: str
    xst: str


def _base() -> str:
    return (
        os.getenv("CAPITAL_API_BASE")
        or os.getenv("CAPITAL_BASE_URL")
        or "https://demo-api-capital.backend-capital.com"
    ).rstrip("/")


def _api_key() -> str:
    return os.getenv("CAPITAL_API_KEY") or os.getenv("CAPITAL_KEY") or ""


def _headers(api_key: Optional[str] = None, tokens: Optional[Tokens] = None) -> dict:
    h = {
        "X-CAP-API-KEY": api_key or _api_key(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if tokens:
        h["CST"] = tokens.cst
        h["X-SECURITY-TOKEN"] = tokens.xst
    return h


def login() -> Tokens:
    url = _base() + "/api/v1/session"
    payload = {
        "identifier": os.getenv("CAPITAL_USERNAME") or os.getenv("CAPITAL_IDENTIFIER"),
        "password": os.getenv("CAPITAL_PASSWORD"),
    }
    r = requests.post(url, headers=_headers(), json=payload, timeout=DEF_TIMEOUT)
    try:
        r.raise_for_status()
    except Exception:
        raise SystemExit(f"login failed {r.status_code}: {r.text}")
    cst = r.headers.get("CST", "")
    xst = r.headers.get("X-SECURITY-TOKEN", "")
    if not cst or not xst:
        raise SystemExit("login ok mutta puuttuu CST/X-SECURITY-TOKEN headereista")
    return Tokens(cst=cst, xst=xst)


def list_accounts(tokens: Optional[Tokens] = None) -> List[Dict]:
    t = tokens or login()
    url = _base() + "/api/v1/accounts"
    r = requests.get(url, headers=_headers(tokens=t), timeout=DEF_TIMEOUT)
    r.raise_for_status()
    j = r.json()
    items = (
        j.get("accounts") if isinstance(j, dict) else (j if isinstance(j, list) else [])
    )
    out = []
    for a in items or []:
        aid = str(a.get("accountId") or a.get("id") or "")
        out.append(
            {
                "accountId": aid,
                "preferred": bool(
                    a.get("preferred") or a.get("isDefault") or a.get("default", False)
                ),
                "type": a.get("accountType") or a.get("type"),
                "currency": a.get("currency") or a.get("currencyIsoCode"),
                "raw": a,
            }
        )
    return out


def _preferred_account(tokens: Tokens) -> str:
    # 1) ENV-lukitus
    acct = os.getenv("CAPITAL_ACCOUNT_ID")
    if acct:
        return str(acct)
    # 2) /accounts/preferences jos saatavilla
    try:
        url = _base() + "/api/v1/accounts/preferences"
        r = requests.get(url, headers=_headers(tokens=tokens), timeout=DEF_TIMEOUT)
        if r.status_code == 200 and r.text:
            j = r.json()
            pref = (
                j.get("defaultAccountId")
                or j.get("preferredAccountId")
                or j.get("accountId")
            )
            if pref:
                return str(pref)
    except Exception:
        pass
    # 3) fallback: listasta preferred → muuten eka
    lst = list_accounts(tokens)
    for a in lst:
        if a.get("preferred") and a.get("accountId"):
            return a["accountId"]
    return lst[0]["accountId"] if lst else ""


def get_account_snapshot(account_id: Optional[str] = None) -> dict:
    t = login()
    acct = account_id or _preferred_account(t)
    if not acct:
        return {
            "ok": False,
            "error": "no account found (preferences empty and /accounts returned none)",
        }
    lst = list_accounts(t)
    row = next((a for a in lst if a["accountId"] == acct), None)
    if not row:
        return {"ok": False, "error": f"account {acct} not in /accounts"}
    bal = row["raw"].get("balance") or {}
    # Mapataan Capitalin kentät -> snapshot
    return {
        "ok": True,
        "account_id": acct,
        "balance": {
            "balance": float(bal.get("balance", 0.0)),
            "deposit": float(bal.get("deposit", 0.0)),
            "profitLoss": float(bal.get("profitLoss", 0.0)),
            "available": float(bal.get("available", 0.0)),
        },
        # Arvioidaan equity/free_margin jos API ei anna niitä erikseen
        "equity": (
            float(bal.get("balance", 0.0)) + float(bal.get("profitLoss", 0.0))
            if bal
            else None
        ),
        "free_margin": float(bal.get("available", 0.0)) if bal else None,
        "margin": row["raw"].get("margin"),
        "raw": {"account": row["raw"]},
        "ts": __import__("time").time(),
    }


def switch_preferred(account_id: str) -> dict:
    t = login()
    url = _base() + "/api/v1/accounts/preferences"
    payload = {"accountId": str(account_id)}
    r = requests.put(url, headers=_headers(tokens=t), json=payload, timeout=DEF_TIMEOUT)
    if r.status_code not in (200, 201, 204):
        return {"ok": False, "status": r.status_code, "text": r.text}
    return {"ok": True, "status": r.status_code}


def debug_info() -> dict:
    return {
        "base_url": _base(),
        "env_seen": {
            "CAPITAL_API_BASE": os.getenv("CAPITAL_API_BASE"),
            "CAPITAL_BASE_URL": os.getenv("CAPITAL_BASE_URL"),
            "CAPITAL_API_KEY": bool(
                os.getenv("CAPITAL_API_KEY") or os.getenv("CAPITAL_KEY")
            ),
            "CAPITAL_USERNAME": os.getenv("CAPITAL_USERNAME")
            or os.getenv("CAPITAL_IDENTIFIER"),
            "CAPITAL_ACCOUNT_ID": os.getenv("CAPITAL_ACCOUNT_ID"),
        },
    }


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--fn",
        choices=["get-account", "debug", "list-accounts", "switch-preferred"],
        required=True,
    )
    ap.add_argument("--account_id")
    args = ap.parse_args()
    if args.fn == "debug":
        print(json.dumps(debug_info(), ensure_ascii=False, indent=2))
    elif args.fn == "list-accounts":
        t = login()
        print(
            json.dumps(
                {"ok": True, "accounts": list_accounts(t)}, ensure_ascii=False, indent=2
            )
        )
    elif args.fn == "switch-preferred":
        if not args.account_id:
            raise SystemExit("--account_id tarvitaan")
        print(
            json.dumps(switch_preferred(args.account_id), ensure_ascii=False, indent=2)
        )
    elif args.fn == "get-account":
        print(
            json.dumps(
                get_account_snapshot(args.account_id), ensure_ascii=False, indent=2
            )
        )


if __name__ == "__main__":
    main()
