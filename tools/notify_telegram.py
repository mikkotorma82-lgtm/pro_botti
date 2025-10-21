from __future__ import annotations
import os, argparse, json, requests
from tools._dotenv import load_dotenv

load_dotenv()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--chat_id", default=os.getenv("TELEGRAM_CHAT_ID"))
    args = ap.parse_args()

    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    if not (tok and args.chat_id):
        raise SystemExit("TELEGRAM_BOT_TOKEN tai TELEGRAM_CHAT_ID puuttuu.")
    r = requests.post(
        f"https://api.telegram.org/bot{tok}/sendMessage",
        data={"chat_id": args.chat_id, "text": args.text, "parse_mode": "HTML"},
        timeout=30,
    )
    r.raise_for_status()
    print(json.dumps(r.json(), ensure_ascii=False))


if __name__ == "__main__":
    main()
