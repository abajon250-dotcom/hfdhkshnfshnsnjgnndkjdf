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

# Запрещенные префиксы (МТС / Билайн - Питер, Татарстан и т.д.)
# Ты можешь дописать сюда нужные коды (например, 7921, 7922, 7985, 7917, 7919, 7987)
BLOCKED_PREFIXES = [
    "+7921", "+7922",  # Питер
    "+7985", "+7917", "+7919", "+7987", # Москва и область
    "+7927", "+7937", "+7987", # Татарстан и Поволжье
    "+7924", "+7928", # Другие южные/северные
]