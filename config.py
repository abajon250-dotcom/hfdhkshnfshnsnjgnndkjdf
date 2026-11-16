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
CHANNEL_ID       = os.getenv("CHANNEL_ID")
CHANNEL_LINK     = _normalize_tg_link(os.getenv("CHANNEL_LINK"))
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")
DATABASE_URL     = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
SUPPORT_LINK     = _normalize_tg_link(os.getenv("SUPPORT_LINK")) or "https://t.me/telegram"

REF_BONUS           = 0.5
QR_COOLDOWN_MINUTES = 40

# Регулярка для проверки номера (строго +79XXXXXXXXX)
PHONE_REGEX = re.compile(r"^\+79\d{9}$")

# --- БЕЛЫЙ СПИСОК РЕГИОНОВ (МТС и Билайн) ---
# Только эти префиксы МЫ ПРИНИМАЕМ. Остальные МТС/Билайн будут отклонены.
ALLOWED_PREFIXES = [
    "+7495", "+7499",   # Москва
    "+7916", "+7925", "+7926", "+7903", "+7905", "+7909", "+7968", "+7985", "+7989", # МТС/Билайн МО
    "+7812", "+7921", "+7931", "+7962", "+7981",  # Санкт-Петербург
    "+7843", "+7917", "+7919", "+7929", "+7937", "+7950", "+7987",  # Татарстан
]

# Если True — бот блокирует МТС/Билайн из регионов НЕ из белого списка.
# Если False — бот принимает все регионы (фильтр отключён).
ENABLE_REGION_FILTER = True