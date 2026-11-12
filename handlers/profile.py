from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_user, pending_amount

router = Router()


@router.message(F.text.contains("Мой профиль"))
async def profile(msg: Message):
    u = await get_user(msg.from_user.id)
    if not u: return await msg.answer("Нажми /start для регистрации.")

    pending = await pending_amount(msg.from_user.id)
    me = await msg.bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref_{msg.from_user.id}"

    text = (
        f"👤 <b>Мой профиль</b>\n\n"
        f"🆔 ID: <code>{u['user_id']}</code>\n"
        f"💰 Баланс: <b>${u['balance']:.2f}</b>\n"
        f"⏳ На проверке: <b>${pending:.2f}</b>\n\n"
        f"📊 <b>Статистика</b>\n"
        f"✅ Успешно: <b>{u['successful_orders']}</b>\n"
        f"❌ Неуспешно: <b>{u['failed_orders']}</b>\n\n"
        f"🔗 <b>Реф. ссылка</b>\n<code>{ref_link}</code>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Вывести средства", callback_data="withdraw")]
    ])
    await msg.answer(text, reply_markup=kb, disable_web_page_preview=True)