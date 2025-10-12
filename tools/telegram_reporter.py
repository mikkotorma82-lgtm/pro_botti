import os, sys, json, requests

TOK  = os.getenv("TELEGRAM_BOT_TOKEN","")
CHAT = os.getenv("TELEGRAM_CHAT_ID","")

def notify(msg:str):
    if not (TOK and CHAT): 
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TOK}/sendMessage",
                      data={"chat_id":CHAT,"text":msg,"parse_mode":"HTML"},
                      timeout=10)
    except Exception:
        pass

for ln in sys.stdin:
    ln = ln.strip()
    if not ln:
        continue
    try:
        j = json.loads(ln)
        if isinstance(j, dict) and j.get("ok"):
            if "filled" in j or "preview" in j:
                notify(f"<b>Trade</b> {j}")
    except Exception:
        pass
    print(ln)
