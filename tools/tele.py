import os, requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

def send(msg: str):
    """Lähetä tekstiviesti Telegramiin"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Telegram env muuttujat puuttuu")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except Exception as e:
        print(f"[ERR] Telegram send: {e}")

def send_photo(photo_path: str, caption: str = ""):
    """Lähetä kuva (esim. backtest-kuva, kaavio, screenshot)"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Telegram env muuttujat puuttuu")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, files={"photo": f})
    except Exception as e:
        print(f"[ERR] Telegram send_photo: {e}")
