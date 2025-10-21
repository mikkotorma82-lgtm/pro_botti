from __future__ import annotations
import os, sqlite3, time, json, requests
from pathlib import Path
from tools._dotenv import load_dotenv

load_dotenv()
DB = Path("data/telemetry.sqlite")
DB.parent.mkdir(exist_ok=True)


def _db():
    con = sqlite3.connect(DB)
    con.execute(
        """CREATE TABLE IF NOT EXISTS events(
        ts REAL, kind TEXT, payload TEXT
    )"""
    )
    return con


def log(kind: str, payload: dict):
    con = _db()
    con.execute(
        "INSERT INTO events(ts,kind,payload) VALUES(?,?,?)",
        (time.time(), kind, json.dumps(payload, ensure_ascii=False)),
    )
    con.commit()
    con.close()


def notify(msg: str):
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    cid = os.getenv("TELEGRAM_CHAT_ID")
    if tok and cid:
        try:
            requests.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                data={"chat_id": cid, "text": msg},
                timeout=20,
            )
        except Exception:
            pass
