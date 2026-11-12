import os
import re
from dotenv import load_dotenv
load_dotenv()

def _normalize_tg_link(value: str | None) -> str | None:
    if not value: return None
    v = value.strip()
    if v.startswith("http://") or v.startswith("https://"): return v
    if v.startswith("@"): v = v[1:]
    if v.startswith("t.me/"): return "https://" + v
    return f"https://t.me/{v}"

BOT_TOKEN        = os.getenv("BOT_TOKEN")
ADMIN_IDS        = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
ADMIN_GROUP_ID   = int(os.getenv("ADMIN_GROUP_ID", "0"))
CHANNEL_ID       = (os.getenv("CHANNEL_ID") or "").strip()
CHANNEL_LINK     = _normalize_tg_link(os.getenv("CHANNEL_LINK"))
CRYPTO_PAY_TOKEN = (os.getenv("CRYPTO_PAY_TOKEN") or "").strip()
SUPPORT_LINK     = _normalize_tg_link(os.getenv("SUPPORT_LINK")) or "https://t.me/telegram"

REF_BONUS           = 0.5
MIN_WITHDRAW        = 5.0
QR_COOLDOWN_MINUTES = 40

# Регулярка для проверки номера: строго +79 и 9 цифр
PHONE_REGEX = re.compile(r"^\+79\d{9}$")