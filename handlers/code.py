from aiogram import Router, Bot
from aiogram.filters import StateFilter
from aiogram.types import Message
from aiogram.dispatcher.event.bases import SkipHandler
from database import get_app_awaiting_code, update_app
from config import ADMIN_GROUP_ID

router = Router()

@router.message(StateFilter(None))
async def catch_code(msg: Message, bot: Bot):
    if not msg.text or msg.text.startswith("/"): raise SkipHandler
    app = await get_app_awaiting_code(msg.from_user.id)
    if not app: raise SkipHandler

    await update_app(app["id"], code=msg.text.strip(), status="code_sent", awaiting_code=0)
    await bot.send_message(ADMIN_GROUP_ID, f"💬 <b>Код для заявки #{app['id']}:</b>\n<code>{msg.text.strip()}</code>")
    await msg.answer("✅ Код отправлен администратору.")