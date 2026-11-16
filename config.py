import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN        = os.getenv("BOT_TOKEN")
ADMIN_IDS        = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
ADMIN_GROUP_ID   = int(os.getenv("ADMIN_GROUP_ID", "0"))
CHANNEL_ID       = os.getenv("CHANNEL_ID")
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")
DATABASE_URL     = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")

REF_BONUS           = 0.5
QR_COOLDOWN_MINUTES = 40

# --- БЕЛЫЙ СПИСОК РЕГИОНОВ (МТС и Билайн) ---
# Только эти префиксы МЫ ПРИНИМАЕМ. Остальные МТС/Билайн будут отклонены.
# Москва и МО
ALLOWED_PREFIXES = [
    "+7495", "+7499",   # Москва (городские)
    "+7916", "+7925", "+7926", "+7903", "+7905", "+7909", "+7968", "+7985", "+7989", # МТС/Билайн МО
    # Санкт-Петербург
    "+7812", "+7921", "+7931", "+7962", "+7981",
    # Татарстан
    "+7843", "+7917", "+7919", "+7929", "+7937", "+7950", "+7987",
]

# Если True — бот блокирует МТС/Билайн из регионов НЕ из белого списка.
# Если False — бот принимает все регионы (фильтр отключён).
ENABLE_REGION_FILTER = True