import requests
from loguru import logger

class TelegramBot:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send(self, message, parse_mode="Markdown"):
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode
        }
        try:
            r = requests.post(self.base_url, data=payload, timeout=10)
            if r.status_code != 200:
                logger.error(f"Telegram send failed: {r.status_code} {r.text}")
            return r.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send exception: {e}")
            return False

# Yksinkertainen globaalikäyttö
telegram_bot = None

def setup(token, chat_id):
    global telegram_bot
    telegram_bot = TelegramBot(token, chat_id)

def send(msg, markdown=True):
    if telegram_bot is None:
        logger.error("TelegramBot not initialized")
        return False
    return telegram_bot.send(msg, parse_mode="Markdown" if markdown else None)
