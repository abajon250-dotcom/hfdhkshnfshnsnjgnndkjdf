from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS, CHANNEL_ID, SUPPORT_LINK
from database import create_user
from keyboards import sub_kb, main_menu_kb

router = Router()

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    referrer_id = None
    parts = msg.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            ref = int(parts[1][4:])
            if ref != msg.from_user.id: referrer_id = ref
        except ValueError: pass

    await create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name, referrer_id)

    try:
        m = await msg.bot.get_chat_member(CHANNEL_ID, msg.from_user.id)
        subscribed = m.status not in ("left", "kicked")
    except Exception:
        subscribed = False

    is_admin = msg.from_user.id in ADMIN_IDS
    if subscribed:
        await msg.answer(f"👋 Привет, <b>{msg.from_user.full_name}</b>!\n\nМеню ниже 👇", reply_markup=main_menu_kb(is_admin))
    else:
        await msg.answer(f"👋 Привет, <b>{msg.from_user.full_name}</b>!\n\nДля начала подпишись на канал.", reply_markup=sub_kb())

@router.callback_query(F.data == "check_sub")
async def check_sub(cb: CallbackQuery):
    try:
        m = await cb.bot.get_chat_member(CHANNEL_ID, cb.from_user.id)
        ok = m.status not in ("left", "kicked")
    except Exception:
        ok = False

    if not ok: return await cb.answer("❌ Подписка не найдена.", show_alert=True)

    await cb.message.edit_text("✅ Подписка подтверждена!")
    await cb.message.answer("Добро пожаловать!", reply_markup=main_menu_kb(cb.from_user.id in ADMIN_IDS))
    await cb.answer()

@router.message(F.text.contains("Поддержка"))
async def support_btn(msg: Message):
    await msg.answer(f"🎧 <b>Поддержка:</b>\n{SUPPORT_LINK}")

@router.message(F.text.contains("Наставники"))
async def mentors_btn(msg: Message):
    await msg.answer("👨‍🏫 Раздел «Наставники» в разработке.")