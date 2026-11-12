import aiohttp
from config import CRYPTO_PAY_TOKEN

API = "https://pay.crypt.bot/api/"


async def get_crypto_balance() -> float:
    """Получает баланс USDT в CryptoBot"""
    async with aiohttp.ClientSession() as s:
        async with s.get(
                API + "getBalance",
                headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
        ) as r:
            data = await r.json()
            if not data.get("ok"):
                raise Exception(data.get("error", "Ошибка API"))

            for b in data["result"]:
                # ИСПРАВЛЕНО: здесь должно быть currency_code, а не asset
                if b.get("currency_code") == "USDT":
                    return float(b.get("available", 0.0))
            return 0.0


async def create_check(amount_usd: float, user_id: int) -> str:
    """Создает чек в USDT на сумму, возвращает ссылку."""
    async with aiohttp.ClientSession() as s:
        async with s.post(
                API + "createCheck",
                headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
                json={"asset": "USDT", "amount": f"{amount_usd:.2f}", "description": f"Withdraw for {user_id}"}
        ) as r:
            data = await r.json()
            if not data.get("ok"):
                raise Exception(data.get("error", "Ошибка создания чека"))
            return data["result"]["bot_check_url"]