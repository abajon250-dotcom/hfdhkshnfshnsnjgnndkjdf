from typing import Any, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config import CHANNEL_ID, ADMIN_IDS

class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: Dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        if user.id in ADMIN_IDS:
            return await handler(event, data)

        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            return await handler(event, data)

        bot = data["bot"]
        try:
            member = await bot.get_chat_member(CHANNEL_ID, user.id)
            ok = member.status not in ("left", "kicked")
        except Exception:
            ok = False

        if not ok:
            from keyboards import sub_kb
            if isinstance(event, CallbackQuery):
                await event.answer("❌ Сначала подпишитесь на канал!", show_alert=True)
            else:
                await event.answer("❌ Подпишитесь на канал и нажмите «Проверить»",
                                   reply_markup=sub_kb())
            return
        return await handler(event, data)   