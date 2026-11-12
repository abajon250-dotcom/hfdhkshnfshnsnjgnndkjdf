from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from states import WorkStates
from database import get_operators, get_operator, create_application, set_admin_message
from keyboards import mode_kb, operators_kb, application_admin_kb, closed_operators_kb
from config import ADMIN_GROUP_ID, PHONE_REGEX

router = Router()


@router.message(F.text.contains("Начать работу"))
async def start_work(msg: Message, state: FSMContext):
    await state.clear()
    await state.set_state(WorkStates.choosing_mode)
    await msg.answer("📞 <b>Начать работу</b>\n\nВыбери режим сдачи:", reply_markup=mode_kb())


@router.callback_query(F.data == "back_main")
async def back_main_inline(cb: CallbackQuery):
    await cb.message.edit_text("🏠 Главное меню внизу 👇")
    await cb.answer()


@router.callback_query(F.data.startswith("mode:"))
async def choose_mode(cb: CallbackQuery, state: FSMContext):
    mode = cb.data.split(":")[1]
    ops = await get_operators()
    field = "number_enabled" if mode == "number" else "qr_enabled"

    if not any(op[field] for op in ops):
        mode_lbl = "Номер" if mode == "number" else "Готовый QR"
        if mode == "number":
            text = "🖐 <b>Приём операторов сейчас закрыт</b>\n\nЗаглядывайте позже — как только приём откроют, кнопки снова заработают."
        else:
            text = "🖐 <b>Готовые QR сейчас не принимаются</b>\n\nГотовые QR принимаются с 04:00 до 21:00 МСК. Приходите в 04:00. Или сдайте номер."

        await state.set_state(WorkStates.choosing_mode)
        await cb.message.edit_text(text, reply_markup=closed_operators_kb(mode))
        return await cb.answer()

    await state.update_data(mode=mode)
    await state.set_state(WorkStates.choosing_operator)
    await cb.message.edit_text("Выбери оператора:", reply_markup=operators_kb(ops, mode, 'regular'))
    await cb.answer()


@router.callback_query(F.data.startswith("cat:"))
async def switch_category(cb: CallbackQuery):
    _, mode, category = cb.data.split(":")
    ops = await get_operators()
    await cb.message.edit_reply_markup(reply_markup=operators_kb(ops, mode, category))
    await cb.answer()


@router.callback_query(F.data.startswith("op_disabled:"))
async def op_disabled_alert(cb: CallbackQuery):
    op_name = cb.data.split(":", 1)[1]
    await cb.answer(f"⚠️ У оператора {op_name} сейчас закрыт приём!\nЗаглядывайте позже.", show_alert=True)


@router.callback_query(F.data.startswith("op:"))
async def choose_operator(cb: CallbackQuery, state: FSMContext):
    _, mode, op_id = cb.data.split(":")
    op = await get_operator(int(op_id))
    await state.update_data(operator_id=op["id"], mode=mode)

    if mode == "number":
        await state.set_state(WorkStates.waiting_number)
        await cb.message.edit_text(
            f"📱 Оператор: <b>{op['name']}</b>\n💰 Цена: <b>${op['price_number']:.2f}</b>\n\nОтправь <b>номер</b> (формат +79XXXXXXXXX):")
    else:
        await state.set_state(WorkStates.waiting_qr_photo)
        await cb.message.edit_text(
            f"🖼 Оператор: <b>{op['name']}</b>\n💰 Цена: <b>${op['price_qr']:.2f}</b>\n\n📸 <b>Шаг 1/2:</b> отправь <b>фото QR-кода</b>:")
    await cb.answer()


@router.message(WorkStates.waiting_number, F.text)
async def receive_number(msg: Message, state: FSMContext, bot: Bot):
    if not PHONE_REGEX.match(msg.text.strip()):
        return await msg.answer("❗ Неверный формат. Отправь строго: <code>+79187382031</code>")

    data = await state.get_data()
    op = await get_operator(data["operator_id"])
    app_id = await create_application(user_id=msg.from_user.id, operator_id=op["id"], mode="number",
                                      phone_number=msg.text.strip())

    text = (
        f"🆕 <b>Заявка #{app_id}</b> [📱 Номер]\n\n"
        f"👤 {msg.from_user.full_name}\n🔗 @{msg.from_user.username or '—'}\n🆔 <code>{msg.from_user.id}</code>\n\n"
        f"📱 Оператор: <b>{op['name']}</b>\n☎️ Номер: <code>{msg.text.strip()}</code>\n💰 Цена: ${op['price_number']:.2f}"
    )

    sent = await bot.send_message(ADMIN_GROUP_ID, text, reply_markup=application_admin_kb(app_id, "number"))
    await set_admin_message(app_id, ADMIN_GROUP_ID, sent.message_id)

    await state.clear()
    await msg.answer("✅ Заявка отправлена на проверку.")


@router.message(WorkStates.waiting_qr_photo, F.photo)
async def qr_photo(msg: Message, state: FSMContext):
    await state.update_data(qr_photo_id=msg.photo[-1].file_id)
    await state.set_state(WorkStates.waiting_qr_number)
    await msg.answer("✅ Фото получено.\n\n📱 <b>Шаг 2/2:</b> отправь <b>номер от QR</b> (формат +79XXXXXXXXX):")


@router.message(WorkStates.waiting_qr_photo)
async def qr_photo_bad(msg: Message):
    await msg.answer("❗ Отправь именно <b>фото</b> QR-кода.")


@router.message(WorkStates.waiting_qr_number, F.text)
async def qr_number(msg: Message, state: FSMContext, bot: Bot):
    if not PHONE_REGEX.match(msg.text.strip()):
        return await msg.answer("❗ Неверный формат. Отправь строго: <code>+79187382031</code>")

    data = await state.get_data()
    op = await get_operator(data["operator_id"])
    app_id = await create_application(user_id=msg.from_user.id, operator_id=op["id"], mode="qr",
                                      qr_photo_id=data["qr_photo_id"], qr_number=msg.text.strip())

    caption = (
        f"🆕 <b>Заявка #{app_id}</b> [🖼 QR]\n\n"
        f"👤 {msg.from_user.full_name}\n🔗 @{msg.from_user.username or '—'}\n🆔 <code>{msg.from_user.id}</code>\n\n"
        f"📱 Оператор: <b>{op['name']}</b>\n🔢 Номер QR: <code>{msg.text.strip()}</code>\n💰 Цена: ${op['price_qr']:.2f}"
    )

    sent = await bot.send_photo(ADMIN_GROUP_ID, photo=data["qr_photo_id"], caption=caption,
                                reply_markup=application_admin_kb(app_id, "qr"))
    await set_admin_message(app_id, ADMIN_GROUP_ID, sent.message_id)

    await state.clear()
    await msg.answer("✅ Заявка отправлена на проверку.")