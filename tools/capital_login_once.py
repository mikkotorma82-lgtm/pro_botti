#!/usr/bin/env python3
from __future__ import annotations
import sys, time, json
from tools.capital_session import capital_rest_login

def main():
    try:
        sess, base = capital_rest_login()
        # tokenit ovat jo tallessa sessioheaderissa; capital_session tallentaa ne state/capital_session.json:iin
        cst = sess.headers.get("CST")
        xsec = sess.headers.get("X-SECURITY-TOKEN")
        print("[OK] Capital login warm-up complete")
        print("BASE:", base)
        print("CST head:", (cst or "")[:8], "SEC head:", (xsec or "")[:8])
        print("Session cached to state/capital_session.json (and cookies.pkl)")
        sys.exit(0)
    except Exception as e:
        print("[FAIL]", e, file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
