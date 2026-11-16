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
QR_COOLDOWN_MINUTES = 40

PHONE_REGEX = re.compile(r"^\+79\d{9}$")

ALLOWED_PREFIXES = [
    "+7495", "+7499",
    "+7916", "+7925", "+7926", "+7903", "+7905", "+7909", "+7968", "+7985", "+7989",
    "+7812", "+7921", "+7931", "+7962", "+7981",
    "+7843", "+7917", "+7919", "+7929", "+7937", "+7950", "+7987",
]
ENABLE_REGION_FILTER = True