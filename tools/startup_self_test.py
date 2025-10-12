import importlib, sys, pathlib, json, time

REQ_IMPORTS = [
    "tools.live_daemon",
]

MODELS = [
    "models/current.joblib",
]

def must(ok, msg):
    if not ok:
        print(f"[SELFTEST][FAIL] {msg}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"[SELFTEST][OK] {msg}")

def main():
    print(f"[SELFTEST] begin {time.strftime('%Y-%m-%d %H:%M:%S')}")
    for m in REQ_IMPORTS:
        importlib.import_module(m)
        must(True, f"import {m}")

    for path in MODELS:
        p = pathlib.Path(path)
        must(p.exists() and p.stat().st_size > 0, f"model exists & non-empty: {path}")

    from tools.live_daemon import should_send_daily_digest
    must(callable(should_send_daily_digest), "should_send_daily_digest callable")

    print("[SELFTEST] ok")

if __name__ == "__main__":
    main()
