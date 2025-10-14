#!/usr/bin/env python3
"""
Telegram notification utilities
"""
import os
import requests
from typing import Optional


def send_notification(message: str, parse_mode: str = 'Markdown') -> bool:
    """
    Send a notification via Telegram bot
    
    Args:
        message: Message text to send
        parse_mode: Message formatting (Markdown or HTML)
    
    Returns:
        True if sent successfully, False otherwise
    """
    # Check if Telegram is enabled
    if os.getenv('TELEGRAM_ENABLE', '0') != '1':
        return False
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    
    if not bot_token or not chat_id:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': parse_mode
        }
        
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
        
    except Exception as e:
        print(f"⚠️  Telegram notification failed: {e}")
        return False


def send_photo(photo_path: str, caption: Optional[str] = None) -> bool:
    """
    Send a photo via Telegram bot
    
    Args:
        photo_path: Path to photo file
        caption: Optional caption for the photo
    
    Returns:
        True if sent successfully, False otherwise
    """
    # Check if Telegram is enabled
    if os.getenv('TELEGRAM_ENABLE', '0') != '1':
        return False
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    
    if not bot_token or not chat_id:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        
        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': chat_id}
            if caption:
                data['caption'] = caption
            
            response = requests.post(url, files=files, data=data, timeout=30)
            return response.status_code == 200
            
    except Exception as e:
        print(f"⚠️  Telegram photo send failed: {e}")
        return False


if __name__ == '__main__':
    # Test notification
    import sys
    message = sys.argv[1] if len(sys.argv) > 1 else "Test notification from Pro Botti"
    success = send_notification(message)
    print(f"{'✅' if success else '❌'} Notification {'sent' if success else 'failed'}")
