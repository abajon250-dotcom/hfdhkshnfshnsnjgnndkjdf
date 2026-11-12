from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta
from states import AdminStates
from database import *
from keyboards import admin_panel_kb, operator_edit_kb, reject_reason_kb, application_admin_kb
from config import ADMIN_IDS, ADMIN_GROUP_ID, REF_BONUS, QR_COOLDOWN_MINUTES

router = Router()


def is_admin(uid: int) -> bool: return uid in ADMIN_IDS


async def safe_edit_app_message(message: Message, new_status_text: str, reply_markup):
    try:
        if message.photo:
            await message.edit_caption(caption=f"{message.caption or ''}\n\n{new_status_text}",
                                       reply_markup=reply_markup)
        else:
            await message.edit_text(text=f"{message.html_text}\n\n{new_status_text}", reply_markup=reply_markup)
    except Exception:
        await message.reply(new_status_text, reply_markup=reply_markup)


@router.message(F.text.contains("Админ-панель"))
async def panel_msg(msg: Message):
    if not is_admin(msg.from_user.id): return
    await msg.answer("👑 <b>Админ-панель</b>", reply_markup=admin_panel_kb(await get_operators()))


@router.callback_query(F.data == "close_admin")
async def close_admin(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.message.delete()
    await cb.answer()


@router.callback_query(F.data.startswith("adm_op:"))
async def op_edit(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    op = await get_operator(int(cb.data.split(":")[1]))
    await cb.message.edit_text(
        f"⚙️ <b>{op['name']}</b>\n\n📱 Номер: {'🟢 вкл' if op['number_enabled'] else '🔴 выкл'} — ${op['price_number']:.2f}\n🖼 QR: {'🟢 вкл' if op['qr_enabled'] else '🔴 выкл'} — ${op['price_qr']:.2f}",
        reply_markup=operator_edit_kb(op))
    await cb.answer()


@router.callback_query(F.data.startswith("adm_tog:"))
async def op_toggle(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    _, op_id, field = cb.data.split(":")
    await toggle_operator(int(op_id), field)
    await cb.message.edit_reply_markup(reply_markup=operator_edit_kb(await get_operator(int(op_id))))
    await cb.answer("Изменено")


@router.callback_query(F.data.startswith("adm_price:"))
async def op_price(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    _, op_id, field = cb.data.split(":")
    await state.set_state(AdminStates.waiting_price)
    await state.update_data(op_id=int(op_id), field=field)
    await cb.message.answer(f"Введи новую цену (<b>{field}</b>) числом:")
    await cb.answer()


@router.message(AdminStates.waiting_price)
async def save_price(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    try:
        price = float(msg.text.replace(",", "."))
    except:
        return await msg.answer("❗ Некорректная цена.")
    data = await state.get_data()
    await update_operator_price(data["op_id"], data["field"], price)
    await state.clear()
    await msg.answer(f"✅ Сохранено. Новая цена: <b>${price:.2f}</b>",
                     reply_markup=operator_edit_kb(await get_operator(data["op_id"])))


@router.callback_query(F.data == "adm_stats_day")
async def stats_day(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    ok, fail, total = await stats_today()
    await cb.message.answer(
        f"📊 <b>Статистика за сегодня</b>\n\n✅ Успешных: <b>{ok}</b>\n❌ Неуспешных: <b>{fail}</b>\n💰 Сумма за сутки: <b>${total:.2f}</b>")
    await cb.answer()


@router.callback_query(F.data == "adm_stats_total")
async def stats_total_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    users, balance, apps = await stats_total()
    await cb.message.answer(
        f"🌐 <b>Общая статистика</b>\n\n👥 Юзеров: <b>{users}</b>\n💰 Баланс: <b>${balance:.2f}</b>\n📦 Заявок: <b>{apps}</b>")
    await cb.answer()


@router.callback_query(F.data == "adm_broadcast")
async def broadcast_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.set_state(AdminStates.waiting_broadcast)
    await cb.message.answer("📣 Отправь сообщение для рассылки:")
    await cb.answer()


@router.message(AdminStates.waiting_broadcast)
async def do_broadcast(msg: Message, state: FSMContext, bot: Bot):
    if not is_admin(msg.from_user.id): return
    await state.clear()
    ids = await all_user_ids()
    sent = 0
    for uid in ids:
        try:
            if msg.photo:
                await bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.html_text)
            else:
                await bot.send_message(uid, msg.html_text)
            sent += 1
        except:
            pass
    await msg.answer(f"✅ Рассылка завершена. Доставлено: {sent}")


@router.callback_query(F.data.startswith("adm_accept:"))
async def accept(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    if not app or app["status"] in ('accepted', 'rejected', 'cancelled'): return await cb.answer("Уже обработано",
                                                                                                 show_alert=True)

    op = await get_operator(app["operator_id"])
    price = op["price_number"] if app["mode"] == "number" else op["price_qr"]

    if app["mode"] == "number":
        await update_app(app_id, status="accepted", awaiting_code=0, processed_at=datetime.utcnow())
        await add_balance(app["user_id"], price)
        try:
            await bot.send_message(app["user_id"], f"✅ <b>Заявка #{app_id} принята!</b>\n💰 +${price:.2f} на баланс.")
        except:
            pass
    else:
        payout_at = (datetime.utcnow() + timedelta(minutes=QR_COOLDOWN_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
        await update_app(app_id, status="accepted", awaiting_code=0, payout_at=payout_at,
                         processed_at=datetime.utcnow())
        try:
            await bot.send_message(app["user_id"],
                                   f"👏 <b>Номер принят в работу</b>\n\n🤙 Номер: <code>{app['qr_number']}</code>\n📌 Заказ: <b>#{app_id}</b>\n\nОфис взял QR в работу. О результате сообщим.")
        except:
            pass

    await increment_orders(app["user_id"], True)
    u = await get_user(app["user_id"])
    if u and u["referrer_id"]:
        await add_balance(u["referrer_id"], REF_BONUS)
        try:
            await bot.send_message(u["referrer_id"], f"💸 Реф. бонус: <b>+${REF_BONUS:.2f}</b>")
        except:
            pass

    await safe_edit_app_message(cb.message, f"✅ Заявка #{app_id} — <b>ПРИНЯТА</b>",
                                application_admin_kb(app_id, app["mode"], "accepted"))
    await cb.answer("Принято")


@router.callback_query(F.data.startswith("adm_cancel:"))
async def cancel_app(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    if not app or app["status"] != 'pending': return await cb.answer("Уже обработано", show_alert=True)

    await update_app(app_id, status="cancelled", processed_at=datetime.utcnow())
    try:
        await bot.send_message(app["user_id"], f"⏹ <b>Заявка #{app_id} отменена администратором.</b>")
    except:
        pass

    await safe_edit_app_message(cb.message, f"⏹ Заявка #{app_id} — <b>ОТМЕНЕНА</b>",
                                application_admin_kb(app_id, app["mode"], "cancelled"))
    await cb.answer("Отменено")


@router.callback_query(F.data.startswith("adm_code:"))
async def request_code(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    await update_app(app_id, status="code_requested", awaiting_code=1)
    try:
        await bot.send_message(app["user_id"],
                               f"💬 Админ запросил <b>код</b> для заявки #{app_id}.\nОтправь его одним сообщением.")
    except:
        return await cb.answer("Юзер заблокировал бота", show_alert=True)

    await safe_edit_app_message(cb.message, "💬 <b>Запрошен код</b>",
                                application_admin_kb(app_id, app["mode"], "code_requested"))
    await cb.answer("Запрос отправлен")


@router.callback_query(F.data.startswith("adm_reject:"))
async def reject(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)

    if app["mode"] == "number":
        await state.set_state(AdminStates.waiting_reject_reason)
        await state.update_data(reject_app_id=app_id)
        await cb.message.answer(f"✍️ Введите <b>причину отклонения</b> для заявки #{app_id} (одним сообщением):")
        await cb.answer()
    else:
        await cb.message.edit_reply_markup(reply_markup=reject_reason_kb(app_id))
        await cb.answer("Выбери причину")


@router.message(AdminStates.waiting_reject_reason)
async def process_reject_reason(msg: Message, state: FSMContext, bot: Bot):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    app_id = data.get("reject_app_id")
    await state.clear()
    if not app_id or not msg.text: return await msg.answer("⚠️ Заявка не найдена или пустая причина.")
    await _finalize_reject(msg, int(app_id), msg.text.strip(), bot)


@router.callback_query(F.data.startswith("adm_back:"))
async def reject_back(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    await cb.message.edit_reply_markup(reply_markup=application_admin_kb(app_id, app["mode"], app["status"]))
    await cb.answer()


@router.callback_query(F.data.startswith("adm_reason:"))
async def reject_with_reason(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    _, app_id, reason = cb.data.split(":")
    await _finalize_reject(cb.message, int(app_id), reason, bot)
    await cb.answer("Отклонено")


async def _finalize_reject(message: Message, app_id: int, reason: str, bot: Bot):
    app = await get_application(app_id)
    if not app or app["status"] in ("rejected", "accepted", "cancelled"): return

    await update_app(app_id, status="rejected", awaiting_code=0, reject_reason=reason, processed_at=datetime.utcnow())
    await increment_orders(app["user_id"], False)

    op = await get_operator(app["operator_id"])
    phone = app["qr_number"] if app["mode"] == "qr" else app["phone_number"]

    if app["mode"] == "number":
        try:
            await bot.send_message(app["user_id"],
                                   f"❌ <b>Заявка #{app_id} отклонена.</b>\n☎️ Номер: <code>{phone}</code>\n\n<b>Причина:</b> {reason}")
        except:
            pass
    else:
        price_qr = op["price_qr"]
        if reason == "block":
            u = await get_user(app["user_id"])
            fine = min(price_qr, max(0.0, u["balance"] if u else 0.0))
            if fine > 0: await add_balance(app["user_id"], -fine)

            msg_text = f"🔒 <b>Ваш номер {phone} заблокирован.</b>\nС баланса списано <b>${fine:.2f}</b>." if fine > 0 else f"🔒 <b>Ваш номер {phone} заблокирован.</b>\nНедостаточно средств для списания."
            try:
                await bot.send_message(app["user_id"], msg_text)
            except:
                pass
        elif reason == "slet":
            try:
                await bot.send_message(app["user_id"], f"❌ <b>Ваш номер {phone} слетел.</b>")
            except:
                pass

    reason_lbl = {"block": "Блок", "slet": "Слет"}.get(reason, reason)
    await safe_edit_app_message(message, f"❌ Заявка #{app_id} — <b>ОТКЛОНЕНА</b>\n📝 {reason_lbl}",
                                application_admin_kb(app_id, app["mode"], "rejected"))


@router.callback_query(F.data.startswith("adm_undo_accept:"))
async def undo_accept(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    if app["status"] != 'accepted': return

    op = await get_operator(app["operator_id"])
    price = op["price_number"] if app["mode"] == "number" else op["price_qr"]
    u = await get_user(app["user_id"])
    deduct = min(price, max(0.0, u["balance"] if u else 0.0))
    if deduct > 0: await add_balance(app["user_id"], -deduct)

    await update_app(app_id, status="pending", payout_at=None, processed_at=None)
    await increment_orders(app["user_id"], True, -1)

    if u and u["referrer_id"]: await add_balance(u["referrer_id"], -REF_BONUS)

    try:
        await bot.send_message(app["user_id"], f"⚠️ <b>Заявка #{app_id} возвращена на проверку.</b>")
    except:
        pass
    await safe_edit_app_message(cb.message, f"🔄 Заявка #{app_id} — <b>ВОЗВРАЩЕНА</b>",
                                application_admin_kb(app_id, app["mode"], "pending"))
    await cb.answer("Отменено")


@router.callback_query(F.data.startswith("adm_undo_reject:"))
async def undo_reject(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    if app["status"] != 'rejected': return

    if app["reject_reason"] == "block":
        op = await get_operator(app["operator_id"])
        await add_balance(app["user_id"], op["price_qr"])

    await update_app(app_id, status="pending", reject_reason=None, processed_at=None)
    await increment_orders(app["user_id"], False, -1)

    try:
        await bot.send_message(app["user_id"], f"⚠️ <b>Заявка #{app_id} восстановлена.</b>")
    except:
        pass
    await safe_edit_app_message(cb.message, f"🔄 Заявка #{app_id} — <b>ВОССТАНОВЛЕНА</b>",
                                application_admin_kb(app_id, app["mode"], "pending"))
    await cb.answer("Восстановлено")


@router.callback_query(F.data.startswith("adm_undo_cancel:"))
async def undo_cancel(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    if app["status"] != 'cancelled': return

    await update_app(app_id, status="pending", processed_at=None)
    try:
        await bot.send_message(app["user_id"], f"⚠️ <b>Заявка #{app_id} восстановлена.</b>")
    except:
        pass
    await safe_edit_app_message(cb.message, f"🔄 Заявка #{app_id} — <b>ВОССТАНОВЛЕНА</b>",
                                application_admin_kb(app_id, app["mode"], "pending"))
    await cb.answer("Восстановлено")