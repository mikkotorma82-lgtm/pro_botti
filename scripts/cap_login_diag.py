#!/usr/bin/env python3
"""
Capital.com login diagnostinen skripti.

Käyttö:
  export CAPITAL_API_BASE=https://api-capital.backend-capital.com
  export CAPITAL_API_KEY=...
  export CAPITAL_USERNAME=...
  export CAPITAL_PASSWORD=...
  # (valinnainen) export CAPITAL_TOTP=123456
  python -m scripts.cap_login_diag

Tulostaa selkeän yhteenvedon molempien endpointtien ( /api/v1/session ja /session ) yrityksistä.
"""
from __future__ import annotations
import os, time, textwrap
import requests
from typing import Dict, Any

REQUIRED = ["CAPITAL_API_BASE", "CAPITAL_API_KEY", "CAPITAL_USERNAME", "CAPITAL_PASSWORD"]

def short(s: str | None, keep: int = 4) -> str:
    if not s:
        return "<empty>"
    if len(s) <= keep*2:
        return s
    return f"{s[:keep]}...{s[-keep:]} (len={len(s)})"

def env_report() -> None:
    print("== ENV CHECK ==")
    missing = False
    for k in REQUIRED:
        v = os.getenv(k, "")
        ok = bool(v.strip())
        print(f"{k}: {'SET' if ok else 'MISSING'}")
        if not ok:
            missing = True
    if missing:
        print("\n[FAIL] Puuttuvia ympäristömuuttujia – lisää ne secrets.env:iin ja lataa (set -a; source secrets.env; set +a)")
        exit(2)
    opt = os.getenv("CAPITAL_TOTP")
    if opt:
        print("CAPITAL_TOTP: SET (optional)")
    else:
        print("CAPITAL_TOTP: (not set, oletetaan ettei 2FA TOTP vaadita)")

def do_login(base: str, api_key: str, username: str, password: str, totp: str | None, path: str) -> Dict[str, Any]:
    url = base.rstrip("/") + path
    body: Dict[str, Any] = {
        "identifier": username,
        "password": password,
        "encryptedPassword": False
    }
    headers = {
        "X-CAP-API-KEY": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": "capital-login-diag/0.1"
    }
    if totp:
        # Capital näyttää hyväksyvän joko bodyssa tai headerissa; laitetaan molemmat
        body["totp"] = totp
        headers["X-TOTP"] = totp

    started = time.time()
    try:
        r = requests.post(url, json=body, headers=headers, timeout=30)
    except requests.RequestException as e:
        return {"path": path, "exception": str(e)}
    elapsed = time.time() - started
    return {
        "path": path,
        "status": r.status_code,
        "elapsed_ms": int(elapsed*1000),
        "resp_text": r.text[:400],
        "cst": r.headers.get("CST"),
        "x_security_token": r.headers.get("X-SECURITY-TOKEN"),
        "raw_headers": {k: v for k, v in r.headers.items()},
    }

def interpret(result: Dict[str, Any]) -> str:
    if "exception" in result:
        return f"PYTHON REQUEST ERROR: {result['exception']}"
    status = result.get("status")
    txt = result.get("resp_text","")
    cst = result.get("cst")
    sec = result.get("x_security_token")
    # Yleisiä tulkintoja
    if status == 200:
        if cst and sec:
            return "SUCCESS: CST ja X-SECURITY-TOKEN saatu."
        return "PARTIAL: 200, mutta CST tai X-SECURITY-TOKEN puuttuu (WAF / väärä endpoint / header?)."
    if status == 400:
        if "error.null.client.token" in txt:
            return "FAIL 400 error.null.client.token → API key tai body ei kelpaa TAI TOTP puuttuu kun vaaditaan."
        if "error.authentication.failed" in txt:
            return "FAIL 400 authentication failed → väärä username/password (API key password)."
        return "FAIL 400 (tarkista password = API key password, ei normaali tilisalasana)."
    if status == 401:
        return "FAIL 401 Unauthorized → usein väärä API key header tai tilillä ei API-oikeuksia."
    if status == 403:
        return "FAIL 403 Forbidden → IP tai avain estetty / ei oikeuksia."
    if status == 429:
        return "FAIL 429 Too Many Requests → odota 60–120s ja kokeile uudestaan."
    if status and status >= 500:
        return f"SERVER ERROR {status} → palvelinongelma / WAF."
    return f"UNKNOWN (status={status})"

def main():
    env_report()
    base = os.getenv("CAPITAL_API_BASE","")
    api_key = os.getenv("CAPITAL_API_KEY","")
    username = os.getenv("CAPITAL_USERNAME","")
    password = os.getenv("CAPITAL_PASSWORD","")
    totp = os.getenv("CAPITAL_TOTP","").strip() or None

    print("\n== REDACTED INPUTS ==")
    print(f"BASE: {base}")
    print(f"API KEY: {short(api_key)}")
    print(f"USERNAME: {username}")
    print(f"PASSWORD: {short(password)}")
    if totp:
        print(f"TOTP: {totp} (will be sent)")

    attempts = ["/api/v1/session", "/session"]
    results = []
    print("\n== LOGIN ATTEMPTS ==")
    for p in attempts:
        print(f"--> Trying {p}")
        res = do_login(base, api_key, username, password, totp, p)
        results.append(res)
        if "exception" in res:
            print(f"   EXCEPTION: {res['exception']}")
            continue
        print(f"   STATUS: {res['status']} elapsed: {res['elapsed_ms']} ms")
        print(f"   HEADERS: CST={short(res.get('cst'))} X-SECURITY-TOKEN={short(res.get('x_security_token'))}")
        snippet = res.get("resp_text","").replace("\n"," ")
        print(f"   BODY[:200]: {snippet[:200]}")
        interp = interpret(res)
        print(f"   INTERPRET: {interp}")
        if res.get("cst") and res.get("x_security_token"):
            print("   -> Tokens found, stopping further attempts.")
            break
        # Pieni viive ennen seuraavaa
        time.sleep(1.0)

    print("\n== SUMMARY ==")
    for r in results:
        path = r.get("path")
        print(f"{path}: {interpret(r)}")

    print(textwrap.dedent("""
    Next steps:
      - Jos edelleen error.null.client.token:
          * Varmista että CAPITAL_PASSWORD on API KEY PASSWORD (ei tilin normaali salasana).
          * Varmista että avain on LIVE-ympäristössä ja aktiivinen (2FA päällä).
          * Jos tilillä on TOTP pakollinen, export CAPITAL_TOTP=<6-digit> ja aja uudelleen.
      - Jos 429: odota 60–120 sekuntia.
      - Jos 200 mutta puuttuu tokenit: WAF tai väärä endpoint; kokeile vain /session tai varmista ettei välissä ole proxy joka droppaa headerit.
    """).strip())

if __name__ == "__main__":
    main()
