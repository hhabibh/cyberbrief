"""
deliver.py
Delivers the formatted digest to Webex and Telegram.
"""

import os
import requests

WEBEX_MESSAGES_URL = "https://webexapis.com/v1/messages"
TELEGRAM_API_BASE = "https://api.telegram.org"


def send_webex(markdown: str, card: dict | None = None) -> bool:
    """
    Send a message to a Webex space.
    If a card payload is provided, sends it as an Adaptive Card with markdown
    as fallback text for clients that don't support cards.
    Returns True on success, False on failure.
    """
    token = os.environ.get("WEBEX_BOT_TOKEN")
    room_id = os.environ.get("WEBEX_ROOM_ID")

    if not token or not room_id:
        raise EnvironmentError(
            "WEBEX_BOT_TOKEN and WEBEX_ROOM_ID must be set as environment variables."
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "roomId": room_id,
        "markdown": markdown,
    }
    if card:
        payload["attachments"] = [card]

    resp = requests.post(
        WEBEX_MESSAGES_URL,
        json=payload,
        headers=headers,
        timeout=15,
    )

    if resp.status_code == 200:
        print("✅ Webex: message sent successfully.")
        return True
    else:
        print(f"❌ Webex: failed ({resp.status_code}) — {resp.text[:200]}")
        return False


def send_telegram(html: str) -> bool:
    """
    Send an HTML message to a Telegram channel or group.
    Returns True on success, False on failure.
    Telegram messages are split if over 4096 characters.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise EnvironmentError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set as environment variables."
        )

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"

    # Telegram max message length is 4096 characters; split if needed
    chunks = _split_message(html, max_len=4096)
    success = True

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=15)

        if resp.status_code == 200:
            print("✅ Telegram: message chunk sent successfully.")
        else:
            print(f"❌ Telegram: failed ({resp.status_code}) — {resp.text[:200]}")
            success = False

    return success


def _split_message(text: str, max_len: int) -> list[str]:
    """Split a message into chunks of at most max_len characters, on newlines."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > max_len:
            if current:
                chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks
