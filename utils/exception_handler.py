from loguru import logger
from tools.tele import send as send_telegram

def exception_handler(fn, notify=True, fallback=None, retries=0, retry_wait=2):
    """
    Kääri funktio turvallisesti try/catchiin. Logittaa ja ilmoittaa virheistä.
    Palauttaa fallback-arvon virhetilanteessa.
    """
    def wrapper(*args, **kwargs):
        attempts = 0
        while attempts <= retries:
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.error(f"[EXCEPTION] {fn.__name__}: {e}")
                if notify:
                    send_telegram(f"[EXCEPTION] {fn.__name__}: {e}")
                attempts += 1
                if attempts <= retries:
                    import time
                    time.sleep(retry_wait)
        return fallback
    return wrapper
