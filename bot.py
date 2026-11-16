import asyncio, logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart, StateFilter
from aiogram.dispatcher.event.bases import SkipHandler
import re

from config import BOT_TOKEN, ADMIN_IDS, ADMIN_GROUP_ID, REF_BONUS, QR_COOLDOWN_MINUTES, BLOCKED_PREFIXES
from database import *
from keyboards import *
from middlewares.subscription import SubscriptionMiddleware
from cryptobot import get_crypto_balance, create_check


class WorkStates(StatesGroup):
    choosing_operator = State()
    waiting_number = State()
    waiting_qr_photo = State()
    waiting_qr_number = State()
    waiting_code = State()


class AdminStates(StatesGroup):
    waiting_min_withdraw = State()
    waiting_work_time = State()
    waiting_support_link = State()
    waiting_broadcast = State()
    waiting_reject_reason = State()
    waiting_balance_amount = State()
    waiting_balance_user = State()


bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def is_admin(uid: int) -> bool: return uid in ADMIN_IDS


@dp.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    if await is_user_banned(msg.from_user.id):
        return await msg.answer("⛔ Вы заблокированы в этом боте.")

    referrer_id = None
    parts = msg.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            ref = int(parts[1][4:])
            if ref != msg.from_user.id: referrer_id = ref
        except ValueError:
            pass

    await create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name, referrer_id)

    await msg.answer(f"👋 Привет, <b>{msg.from_user.full_name}</b>!\n\nМеню ниже 👇",
                     reply_markup=main_menu_kb(is_admin(msg.from_user.id)))


# --- ПРОФИЛЬ ---
@dp.message(F.text.contains("Мой профиль"))
async def profile(msg: Message):
    u = await get_user(msg.from_user.id)
    if not u: return await msg.answer("Нажми /start.")

    pending = await pending_amount(msg.from_user.id)
    pending_wd = await get_pending_withdrawn(msg.from_user.id)
    withdrawn = await get_total_withdrawn(msg.from_user.id)
    fines = await get_total_fines(msg.from_user.id)
    available = u['balance']
    total_earned = available + pending + pending_wd + withdrawn + fines

    text = (
        f"👤 <b>Мой профиль</b>\n\n"
        f"💰 <b>Заработано:</b> <b>${total_earned:.2f}</b>\n"
        f"├ Доступно к выводу: <b>${available:.2f}</b>\n"
        f"├ На проверке: <b>${pending:.2f}</b>\n"
        f"├ На выводе: <b>${pending_wd:.2f}</b>\n"
        f"├ Выведено: <b>${withdrawn:.2f}</b>\n"
        f"└ Штрафы (блоки): <b>${fines:.2f}</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"✅ Успешно: <b>{u['successful_orders']}</b>\n"
        f"❌ Неуспешно: <b>{u['failed_orders']}</b>\n"
        f"🔄 Всего: <b>{u['successful_orders'] + u['failed_orders']}</b>"
    )
    await msg.answer(text, reply_markup=profile_kb())


@dp.callback_query(F.data == "withdraw_history")
async def withdraw_history(cb: CallbackQuery):
    wds = await get_user_withdrawals(cb.from_user.id)
    if not wds:
        return await cb.answer("У вас пока нет выплат.", show_alert=True)

    text = "💸 <b>История выплат:</b>\n\n"
    for w in wds:
        if w['status'] == 'completed':
            date = w['created_at'].strftime("%d.%m %H:%M")
            text += f"✅ <b>${w['amount']:.2f}</b> — выплачено {date}\n"
            if w['check_url']:
                kb = withdraw_check_kb(w['id'])
                await cb.message.answer(text, reply_markup=kb)
                text = ""
        elif w['status'] == 'pending':
            text += f"⏳ <b>${w['amount']:.2f}</b> — в обработке\n"
        elif w['status'] == 'cancelled':
            text += f"❌ <b>${w['amount']:.2f}</b> — отменено ({w['reject_reason']})\n"
    if text: await cb.message.answer(text)
    await cb.answer()


@dp.callback_query(F.data.startswith("show_check:"))
async def show_check(cb: CallbackQuery):
    w_id = int(cb.data.split(":")[1])
    async with pool.acquire() as conn:
        w = await conn.fetchrow("SELECT check_url FROM withdrawals WHERE id=$1", w_id)
    if w and w['check_url']:
        await cb.message.answer(f"🔗 <b>Ссылка на чек:</b>\n{w['check_url']}")
    else:
        await cb.answer("Чек не найден.", show_alert=True)
    await cb.answer()


# --- ВЫВОД ---
@dp.callback_query(F.data == "withdraw")
async def withdraw(cb: CallbackQuery):
    u = await get_user(cb.from_user.id)
    amount = u["balance"]
    min_wd = float(await get_setting("min_withdraw") or 5.0)

    if amount < min_wd:
        return await cb.answer(f"❌ Минимум для вывода: ${min_wd:.2f}\nБаланс: ${amount:.2f}", show_alert=True)

    await create_withdrawal(cb.from_user.id, amount)
    await cb.message.answer(f"✅ Заявка на вывод <b>${amount:.2f}</b> создана!\nОжидайте выплаты.")
    await bot.send_message(ADMIN_GROUP_ID,
                           f"💸 <b>Новая заявка на вывод!</b>\n👤 @{cb.from_user.username or cb.from_user.id}\n💰 Сумма: <b>${amount:.2f}</b>")
    await cb.answer()


# --- АДМИНКА ---
@dp.message(F.text.contains("Админ-панель"))
async def panel_msg(msg: Message):
    if not is_admin(msg.from_user.id): return await msg.answer("⛔ Нет доступа.")
    await msg.answer("👑 <b>Админ-панель</b>", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "admin_panel")
async def back_to_admin(cb: CallbackQuery):
    await cb.message.edit_text("👑 <b>Админ-панель</b>", reply_markup=admin_panel_kb())


# --- НАСТРОЙКИ ---
@dp.callback_query(F.data == "adm_settings")
async def adm_settings(cb: CallbackQuery):
    min_wd = await get_setting("min_withdraw")
    w_start = await get_setting("work_start")
    w_end = await get_setting("work_end")
    supp = await get_setting("support_link")

    text = (
        f"⚙ <b>Настройки</b>\n\n"
        f"Мин. вывод: <b>${min_wd}</b>\n"
        f"Работа: <b>{w_start} - {w_end}</b>\n"
        f"Связь: <b>{supp}</b>"
    )
    await cb.message.edit_text(text, reply_markup=settings_kb())


@dp.callback_query(F.data.startswith("set_"))
async def setting_edit(cb: CallbackQuery, state: FSMContext):
    action = cb.data.split(":")[0] if ":" in cb.data else cb.data
    if action == "set_min_withdraw":
        await state.set_state(AdminStates.waiting_min_withdraw)
        await cb.message.answer("Введи новую сумму минимального вывода:")
    elif action == "set_work_time":
        await state.set_state(AdminStates.waiting_work_time)
        await cb.message.answer("Введи время работы (пример: <code>08:00-23:00</code>):")
    elif action == "set_support_link":
        await state.set_state(AdminStates.waiting_support_link)
        await cb.message.answer("Введи ссылку на поддержку (пример: https://t.me/manager):")
    await cb.answer()


@dp.message(AdminStates.waiting_min_withdraw)
async def save_min_wd(msg: Message, state: FSMContext):
    try:
        val = float(msg.text)
    except:
        return await msg.answer("Введи число!")
    await set_setting("min_withdraw", str(val))
    await state.clear()
    await msg.answer(f"✅ Мин. вывод изменен на ${val:.2f}", reply_markup=admin_panel_kb())


@dp.message(AdminStates.waiting_work_time)
async def save_work_time(msg: Message, state: FSMContext):
    try:
        start, end = msg.text.split("-")
        await set_setting("work_start", start.strip())
        await set_setting("work_end", end.strip())
        await state.clear()
        await msg.answer(f"✅ График работы: {start} - {end}", reply_markup=admin_panel_kb())
    except:
        await msg.answer("⚠️ Неверный формат. Введи: 08:00-23:00")


@dp.message(AdminStates.waiting_support_link)
async def save_support(msg: Message, state: FSMContext):
    await set_setting("support_link", msg.text)
    await state.clear()
    await msg.answer("✅ Ссылка на связь обновлена.", reply_markup=admin_panel_kb())


# --- ВЫПЛАТЫ ---
@dp.callback_query(F.data == "adm_withdrawals")
async def adm_withdrawals(cb: CallbackQuery):
    ws = await get_pending_withdrawals()
    if not ws: return await cb.answer("Нет активных заявок.")
    await cb.message.edit_text("💸 <b>Заявки на вывод:</b>", reply_markup=withdrawals_kb(ws))


@dp.callback_query(F.data.startswith("adm_pay_w:"))
async def adm_pay_w(cb: CallbackQuery):
    w_id = int(cb.data.split(":")[1])
    async with pool.acquire() as conn:
        w = await conn.fetchrow("SELECT * FROM withdrawals WHERE id=$1", w_id)

    amount = w['amount']
    user_id = w['user_id']

    try:
        crypto_bal = await get_crypto_balance()
    except Exception as e:
        return await cb.answer(f"Ошибка CryptoPay: {e}", show_alert=True)

    if crypto_bal < amount:
        return await cb.answer(f"❌ Недостаточно средств на CryptoBot!\nНужно: ${amount:.2f}\nЕсть: ${crypto_bal:.2f}",
                               show_alert=True)

    try:
        link = await create_check(amount, user_id)
    except Exception as e:
        return await cb.answer(f"Ошибка создания чека: {e}", show_alert=True)

    await complete_withdrawal(w_id, link)
    try:
        await bot.send_message(user_id, f"💸 <b>Ваша выплата готова!</b>\nСумма: <b>${amount:.2f}</b>\nСсылка: {link}",
                               reply_markup=withdraw_check_kb(w_id))
    except:
        pass

    # Статистика админу
    ok, fail, total = await stats_today()
    await cb.message.answer(
        f"✅ Выплата #{w_id} на ${amount:.2f} отправлена.\n\n"
        f"📊 <b>Стата за сегодня:</b>\n"
        f"Заявок: {ok + fail}\nОтстояло: {ok}\nБлоков: {fail}\nВыплачено: ${total:.2f}"
    )
    ws = await get_pending_withdrawals()
    if not ws:
        await cb.message.edit_text("💸 Все заявки обработаны.", reply_markup=admin_panel_kb())
    else:
        await cb.message.edit_reply_markup(reply_markup=withdrawals_kb(ws))
    await cb.answer("Выплачено!")


@dp.callback_query(F.data.startswith("adm_cancel_w:"))
async def adm_cancel_w(cb: CallbackQuery):
    w_id = int(cb.data.split(":")[1])
    await cancel_withdrawal(w_id, "Отменено администратором (сгорело)")
    async with pool.acquire() as conn:
        w = await conn.fetchrow("SELECT user_id, amount FROM withdrawals WHERE id=$1", w_id)

    try:
        await bot.send_message(w['user_id'], f"❌ Заявка на вывод ${w['amount']:.2f} отменена. Средства сгорели.")
    except:
        pass

    await cb.answer("Заявка отменена (деньги списаны).")
    ws = await get_pending_withdrawals()
    if not ws:
        await cb.message.edit_text("💸 Все заявки обработаны.", reply_markup=admin_panel_kb())
    else:
        await cb.message.edit_reply_markup(reply_markup=withdrawals_kb(ws))


# --- ЗАЯВКИ ---
@dp.callback_query(F.data.startswith("adm_user_info:"))
async def adm_user_info(cb: CallbackQuery):
    app_id = int(cb.data.split(":")[1])
    app_data = await get_application(app_id)
    u = await get_user(app_data['user_id'])
    is_banned = await is_user_banned(u['user_id'])

    await cb.message.answer(
        f"👤 <b>Инфо о юзере</b>\n\n"
        f"ID: <code>{u['user_id']}</code>\n"
        f"Юзернейм: @{u['username'] or 'скрыт'}\n"
        f"Баланс: <b>${u['balance']:.2f}</b>\n"
        f"Забанен: {'Да' if is_banned else 'Нет'}",
        reply_markup=user_info_kb(u['user_id'], is_banned)
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_ban:"))
async def ban_user_cb(cb: CallbackQuery):
    user_id = int(cb.data.split(":")[1])
    await ban_user(user_id)
    await cb.message.edit_text(f"🚫 Юзер {user_id} забанен.", reply_markup=admin_panel_kb())
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_unban:"))
async def unban_user_cb(cb: CallbackQuery):
    user_id = int(cb.data.split(":")[1])
    await unban_user(user_id)
    await cb.message.edit_text(f"✅ Юзер {user_id} разбанен.", reply_markup=admin_panel_kb())
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_add_bal:"))
async def add_bal_cb(cb: CallbackQuery, state: FSMContext):
    user_id = int(cb.data.split(":")[1])
    await state.set_state(AdminStates.waiting_balance_amount)
    await state.update_data(user_id=user_id, action="add")
    await cb.message.answer("Введи сумму для начисления:")
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_sub_bal:"))
async def sub_bal_cb(cb: CallbackQuery, state: FSMContext):
    user_id = int(cb.data.split(":")[1])
    await state.set_state(AdminStates.waiting_balance_amount)
    await state.update_data(user_id=user_id, action="sub")
    await cb.message.answer("Введи сумму для списания:")
    await cb.answer()


@dp.message(AdminStates.waiting_balance_amount)
async def process_balance_change(msg: Message, state: FSMContext):
    try:
        amount = float(msg.text)
    except:
        return await msg.answer("Введи число!")
    data = await state.get_data()
    user_id = data['user_id']

    if data['action'] == "add":
        await add_balance(user_id, amount)
        await msg.answer(f"✅ Начислено ${amount:.2f} юзеру {user_id}.", reply_markup=admin_panel_kb())
    else:
        await add_balance(user_id, -amount)
        await msg.answer(f"✅ Списано ${amount:.2f} юзера {user_id}.", reply_markup=admin_panel_kb())
    await state.clear()


# --- РАБОТА И ПРОВЕРКИ ---
@dp.message(F.text.contains("Начать работу"))
async def start_work(msg: Message, state: FSMContext):
    await state.clear()
    if await is_user_banned(msg.from_user.id): return await msg.answer("⛔ Вы заблокированы.")

    # Проверка кулдауна 15 минут
    u = await get_user(msg.from_user.id)
    if u['last_reject_time']:
        diff = (datetime.utcnow() - u['last_reject_time']).total_seconds()
        if diff < 900:
            mins = int((900 - diff) // 60)
            return await msg.answer(f"⚠️ Ваша прошлая заявка была отклонена. Кулдаун: {mins} мин.")

    await state.set_state(WorkStates.choosing_operator)
    await msg.answer("Выбери режим сдачи:", reply_markup=mode_kb())


@dp.message(WorkStates.waiting_number, F.text)
async def receive_number(msg: Message, state: FSMContext):
    phone = msg.text.strip()
    if not re.match(r"^\+79\d{9}$", phone):
        return await msg.answer("❗ Формат: <code>+79187382031</code>")

    if await check_duplicate_number("number", phone):
        return await msg.answer("❌ Этот номер уже находится на проверке или был оплачен.")

    for prefix in BLOCKED_PREFIXES:
        if phone.startswith(prefix):
            return await msg.answer("❌ Данный регион (МТС/Билайн) временно не принимается.")

    data = await state.get_data()
    op = await get_operator(data['operator_id'])
    app_id = await create_application(msg.from_user.id, op['id'], "number", phone_number=phone)

    text = f"🆕 <b>Заявка #{app_id}</b> [Номер]\n👤 @{msg.from_user.username}\n📱 {op['name']}\n☎️ {phone}"
    sent = await bot.send_message(ADMIN_GROUP_ID, text, reply_markup=application_admin_kb(app_id, "number"))
    await set_admin_message(app_id, ADMIN_GROUP_ID, sent.message_id)
    await state.clear()
    await msg.answer("✅ Заявка отправлена.")


@dp.message(WorkStates.waiting_qr_photo, F.photo)
async def qr_photo(msg: Message, state: FSMContext):
    await state.update_data(qr_photo_id=msg.photo[-1].file_id)
    await state.set_state(WorkStates.waiting_qr_number)
    await msg.answer("✅ Фото получено. Отправь номер от QR:")


@dp.message(WorkStates.waiting_qr_number, F.text)
async def qr_number(msg: Message, state: FSMContext):
    qr_num = msg.text.strip()
    if not re.match(r"^\+79\d{9}$", qr_num):
        return await msg.answer("❗ Формат: <code>+79187382031</code>")

    if await check_duplicate_number("qr", qr_num):
        return await msg.answer("❌ Этот QR уже на проверке или оплачен.")

    data = await state.get_data()
    op = await get_operator(data['operator_id'])
    app_id = await create_application(msg.from_user.id, op['id'], "qr", qr_photo_id=data['qr_photo_id'],
                                      qr_number=qr_num)

    caption = f"🆕 <b>Заявка #{app_id}</b> [QR]\n👤 @{msg.from_user.username}\n📱 {op['name']}\n🔢 {qr_num}"
    sent = await bot.send_photo(ADMIN_GROUP_ID, data['qr_photo_id'], caption=caption,
                                reply_markup=application_admin_kb(app_id, "qr"))
    await set_admin_message(app_id, ADMIN_GROUP_ID, sent.message_id)
    await state.clear()
    await msg.answer("✅ Заявка отправлена.")


@dp.callback_query(F.data.startswith("adm_reason:"))
async def adm_reason(cb: CallbackQuery):
    _, app_id, reason = cb.data.split(":")
    app_id = int(app_id)
    app = await get_application(app_id)

    if app["status"] in ("rejected", "accepted", "cancelled"): return

    await update_app(app_id, status="rejected", reject_reason=reason, processed_at=datetime.utcnow())
    await update_last_reject(app["user_id"])
    await increment_orders(app["user_id"], False)

    if reason == "block":
        u = await get_user(app["user_id"])
        op = await get_operator(app["operator_id"])
        fine = min(op['price_qr'], max(0.0, u['balance'] if u else 0.0))
        if fine > 0: await add_balance(app["user_id"], -fine)
        try:
            await bot.send_message(app["user_id"], f"🔒 <b>Номер заблокирован.</b> Списано: ${fine:.2f}")
        except:
            pass
    else:
        try:
            await bot.send_message(app["user_id"], "❌ Ваш номер слетел.")
        except:
            pass

    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.reply(f"❌ Заявка #{app_id} отклонена ({reason}).")


# --- ФОНОВЫЕ ЗАДАЧИ ---
async def payout_worker():
    while True:
        try:
            for app in await pending_payouts():
                if not await try_payout(app["id"]): continue
                op = await get_operator(app["operator_id"])
                price = op["price_qr"] if app["mode"] == "qr" else op["price_number"]
                await add_balance(app["user_id"], price)
                try:
                    await bot.send_message(app["user_id"], f"✅ Материал засчитан! +${price:.2f}")
                except Exception:
                    pass
        except Exception:
            logging.exception("payout_worker error")
        await asyncio.sleep(30)


async def work_scheduler():
    while True:
        try:
            start_str = await get_setting("work_start") or "06:00"
            end_str = await get_setting("work_end") or "19:00"

            now = datetime.utcnow() + timedelta(hours=3)  # МСК
            current_time = now.strftime("%H:%M")

            # Простое сравнение строк работает для формата ЧЧ:ММ
            is_working = start_str <= current_time <= end_str

            ops = await get_operators()
            any_active = any(op["number_active"] or op["qr_active"] for op in ops)

            if is_working and not any_active:
                await set_all_operators(True)
                logging.info("Авто-ворк: ВКЛ")
            elif not is_working and any_active:
                await set_all_operators(False)
                logging.info("Авто-ворк: ВЫКЛ")

        except Exception:
            logging.exception("work_scheduler error")
        await asyncio.sleep(60)


async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    asyncio.create_task(payout_worker())
    asyncio.create_task(work_scheduler())
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot started (Postgres)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())