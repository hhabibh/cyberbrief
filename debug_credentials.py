"""
debug_credentials.py
Checks that .env values are loaded correctly and tests each API independently.
Run with: python debug_credentials.py
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

def check(name):
    val = os.environ.get(name, "")
    if not val:
        print(f"  ❌ {name}: NOT SET")
        return val
    stripped = val.strip()
    has_whitespace = val != stripped
    # Show length and first/last 4 chars only — never prints full secret
    masked = stripped[:4] + "*" * (len(stripped) - 8) + stripped[-4:]
    print(f"  {'⚠️ ' if has_whitespace else '✅'} {name}: length={len(stripped)}"
          f"{' (had leading/trailing whitespace — fixed)' if has_whitespace else ''}"
          f", value={masked}")
    # Return stripped value so API calls use clean token
    os.environ[name] = stripped
    return stripped

print("\n=== Checking .env values ===")
groq_key     = check("GROQ_API_KEY")
webex_token  = check("WEBEX_BOT_TOKEN")
webex_room   = check("WEBEX_ROOM_ID")
tg_token     = check("TELEGRAM_BOT_TOKEN")
tg_chat      = check("TELEGRAM_CHAT_ID")

print("\n=== Testing Webex ===")
if webex_token:
    r = requests.get(
        "https://webexapis.com/v1/people/me",
        headers={"Authorization": f"Bearer {webex_token}"},
        timeout=10,
    )
    if r.status_code == 200:
        data = r.json()
        print(f"  ✅ Token valid — bot name: {data.get('displayName')}, type: {data.get('type')}")
    else:
        print(f"  ❌ Token invalid — HTTP {r.status_code}: {r.text[:200]}")

print("\n=== Testing Telegram ===")
if tg_token:
    r = requests.get(
        f"https://api.telegram.org/bot{tg_token}/getMe",
        timeout=10,
    )
    if r.status_code == 200:
        data = r.json()
        print(f"  ✅ Token valid — bot: @{data['result'].get('username')}")
    else:
        print(f"  ❌ Token invalid — HTTP {r.status_code}: {r.text[:200]}")

if tg_token and tg_chat:
    r = requests.post(
        f"https://api.telegram.org/bot{tg_token}/sendMessage",
        json={"chat_id": tg_chat, "text": "CyberBrief test message ✅"},
        timeout=10,
    )
    if r.status_code == 200:
        print(f"  ✅ Message sent to channel successfully")
    else:
        print(f"  ❌ Send failed — HTTP {r.status_code}: {r.text[:300]}")
