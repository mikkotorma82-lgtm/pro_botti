#!/usr/bin/env python3
from __future__ import annotations
import os, time, json, itertools
import requests

BASE = os.getenv("CAPITAL_API_BASE","").rstrip("/")
API_KEY = os.getenv("CAPITAL_API_KEY","")
USER = os.getenv("CAPITAL_USERNAME","")
PWD  = os.getenv("CAPITAL_PASSWORD","")
TOTP = os.getenv("CAPITAL_TOTP","").strip() or None

PATHS = ["/api/v1/session","/session"]
HEADER_VARIANTS = [
    {"Content-Type":"application/json","Accept":"application/json"},
    {"Content-Type":"application/json"},   # ilman Accept
    {},                                    # minimal
]
HTTP1 = [True, False]  # True = force http1.1 via requests adapter (simplified)
SEND_TOTP = [False, True] if TOTP else [False]

sess = requests.Session()
sess.headers.update({"User-Agent":"cap-login-matrix/1.0"})

def force_http1(sess: requests.Session):
    # requests ei helppoa pakottaa HTTP/1.1 vs 2; käytännössä urllib3 fallback = 1.1
    # Ei tehdä mitään, mutta pidetään paikka.
    pass

def attempt(path, headers, totp, attempt_id):
    url = BASE + path
    body = {
        "identifier": USER,
        "password": PWD,
        "encryptedPassword": False
    }
    h = {"X-CAP-API-KEY": API_KEY}
    h.update(headers)
    if totp:
        body["totp"] = TOTP
        h["X-TOTP"] = TOTP
    t0 = time.time()
    try:
        r = sess.post(url, json=body, headers=h, timeout=30)
    except Exception as e:
        return {"id":attempt_id,"path":path,"headers":h,"totp":bool(totp),"error":str(e)}
    dt = int((time.time()-t0)*1000)
    return {
        "id":attempt_id,
        "path":path,
        "status":r.status_code,
        "ms":dt,
        "cst":r.headers.get("CST"),
        "sec":r.headers.get("X-SECURITY-TOKEN"),
        "body":r.text[:300],
        "sent_headers":h
    }

def interpret(res):
    if "error" in res:
        return "REQUEST_ERROR "+res["error"]
    st = res.get("status")
    body = res.get("body","")
    if st == 200:
        if res.get("cst") and res.get("sec"):
            return "SUCCESS"
        return "200_NO_TOKENS"
    if st == 400 and "error.null.client.token" in body:
        return "NULL_CLIENT_TOKEN"
    if st == 429:
        return "RATE_LIMIT"
    if st == 401:
        return "UNAUTHORIZED"
    return f"STATUS_{st}"

def main():
    missing = [k for k,v in [("BASE",BASE),("API_KEY",API_KEY),("USER",USER),("PWD",PWD)] if not v]
    if missing:
        print("Missing env:", missing); return
    results = []
    attempt_id = 0
    for path, hdrs, totp in itertools.product(PATHS, HEADER_VARIANTS, SEND_TOTP):
        attempt_id += 1
        time.sleep(1.2)  # rauhallinen tahti
        res = attempt(path, hdrs, totp, attempt_id)
        res["tag"] = interpret(res)
        results.append(res)
        print(f"[{attempt_id}] {path} totp={totp} hdrs={list(hdrs.keys()) or 'minimal'} -> {res.get('status')} {res['tag']}")
        if res.get("cst") and res.get("sec"):
            print("Tokens received -> stopping matrix early.")
            break
        if res.get("status") == 429:
            print("Hit rate limit -> sleeping 65s before next variant.")
            time.sleep(65)
    print("\nDetailed failures:")
    for r in results:
        if r.get("cst") and r.get("sec"):
            print(f"- {r['id']} SUCCESS CST/SEC present (path={r['path']})")
            continue
        print(f"- {r['id']} {r['tag']} path={r['path']} status={r.get('status')} body_snippet={r.get('body','')[:80]!r}")
    print("\nSuggestion ladder:")
    print("1. If every tag is NULL_CLIENT_TOKEN -> password or key mismatch (recreate key).")
    print("2. If only minimal headers succeed later, Accept/charset disturbed WAF.")
    print("3. If RATE_LIMIT appears early, extend pause between attempts (export YF_DELAY not relevant here).")
    print("4. If UNAUTHORIZED appears, check key active on LIVE (not demo).")
    print("5. Revoke key, generate new, re-run this script after 2 minutes idle.")
    print("6. Still failing -> capture a successful Postman raw HTTP (export) and compare headers (share only redacted).")

if __name__ == "__main__":
    main()
