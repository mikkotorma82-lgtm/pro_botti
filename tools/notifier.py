#!/usr/bin/env python3
from __future__ import annotations
import os, urllib.parse, urllib.request, json, time
from typing import Optional, List

def _tg_token() -> Optional[str]:
    return os.getenv("TELEGRAM_BOT_TOKEN")
def _tg_chat() -> Optional[str]:
    return os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(text: str, disable_web_page_preview: bool = True) -> bool:
    tok, chat = _tg_token(), _tg_chat()
    if not tok or not chat:
        return False
    try:
        data = {"chat_id": chat, "text": text[:3900], "disable_web_page_preview": disable_web_page_preview}
        body = urllib.parse.urlencode(data).encode()
        url = f"https://api.telegram.org/bot{tok}/sendMessage"
        req = urllib.request.Request(url, data=body)
        with urllib.request.urlopen(req, timeout=10) as r:
            json.loads(r.read() or b"{}")
        return True
    except Exception:
        return False

def send_big(title: str, lines: List[str], max_lines: int = 80):
    head = f"{title}\n"
    if not lines:
        send_telegram(head); return
    chunk, cnt, acc = [], 0, 0
    for ln in lines[:max_lines]:
        chunk.append(ln); cnt += 1; acc += len(ln) + 1
        if acc > 2800 or cnt >= 60:
            send_telegram(head + "\n".join(chunk))
            chunk, cnt, acc = [], 0, 0
            time.sleep(0.2)
    if chunk:
        send_telegram(head + "\n".join(chunk))
