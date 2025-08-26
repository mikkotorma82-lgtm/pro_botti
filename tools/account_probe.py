from __future__ import annotations
import os, json, argparse
from tools.broker_capital import (
    CapitalClient,
    CapitalError,
)  # paketointi varmistaa ._dotenv-latauksen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account_id", default=os.getenv("CAPITAL_ACCOUNT_ID"))
    args = ap.parse_args()
    cli = CapitalClient()
    cli.login()
    m = cli.metrics(args.account_id)
    print(json.dumps({"status": "ok", "metrics": m}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
