import os, sys, requests
def send(msg):
    tok=os.getenv("TELEGRAM_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
    if tok and chat: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", data={"chat_id":chat,"text":msg[:3900]})
if __name__=="__main__": send(" ".join(sys.argv[1:]) or "ping")
