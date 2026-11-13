import asyncio, logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.dispatcher.event.bases import SkipHandler
import aiosqlite

from config import BOT_TOKEN, ADMIN_IDS, ADMIN_GROUP_ID, REF_BONUS, QR_COOLDOWN_MINUTES, PHONE_REGEX, SUPPORT_LINK, \
    CHANNEL_ID
from database import *
from keyboards import *
from middlewares.subscription import SubscriptionMiddleware
from cryptobot import get_crypto_balance, create_check

E_GREETING_HTML = '<tg-emoji emoji-id="5258501105293205250">👋</tg-emoji>'
E_START_WORK_HTML = '<tg-emoji emoji-id="5258337316715373336">📞</tg-emoji>'
E_PROFILE_HTML = '<tg-emoji emoji-id="5258011929993026890">👤</tg-emoji>'
E_SUPPORT_HTML = '<tg-emoji emoji-id="5316727448644103237">🎧</tg-emoji>'
E_WALLET_HTML = '<tg-emoji emoji-id="5258204546391351475">💳</tg-emoji>'
E_STATS_HTML = '<tg-emoji emoji-id="5258330865674494479">📊</tg-emoji>'
E_SUCCESS_HTML = '<tg-emoji emoji-id="5260416304224936047">✅</tg-emoji>'
E_FAIL_HTML = '<tg-emoji emoji-id="5260342697075416641">❌</tg-emoji>'
E_TOTAL_HTML = '<tg-emoji emoji-id="5258057130228849960">🌐</tg-emoji>'
E_CALENDAR_HTML = '<tg-emoji emoji-id="5258105663359294787">📅</tg-emoji>'
E_MONEY_HTML = '<tg-emoji emoji-id="5258368777350816286">💰</tg-emoji>'
E_BLOCK_HTML = '<tg-emoji emoji-id="5258318620722733379">🚫</tg-emoji>'
E_NUM_ACCEPTED_HTML = '<tg-emoji emoji-id="5258501105293205250">👏</tg-emoji>'
E_PHONE_HTML = '<tg-emoji emoji-id="5258337316715373336">📱</tg-emoji>'
E_ORDER_HTML = '<tg-emoji emoji-id="5258461531464539536">📌</tg-emoji>'
E_BROADCAST_HTML = '<tg-emoji emoji-id="5258089153505009279">📣</tg-emoji>'
E_DOWN_HTML = '<tg-emoji emoji-id="5231102735817918643">👇</tg-emoji>'
E_LINK_HTML = '<tg-emoji emoji-id="5260730055880876557">🔗</tg-emoji>'
E_NOT_ACCEPT_HTML = '<tg-emoji emoji-id="5260249440450520061">🖐</tg-emoji>'


class WorkStates(StatesGroup):
    choosing_operator = State()
    waiting_number = State()
    waiting_qr_photo = State()
    waiting_qr_number = State()
    waiting_code = State()


class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_price = State()
    waiting_reject_reason = State()
    waiting_new_name = State()


class SupportStates(StatesGroup):
    waiting_msg = State()
    waiting_reply = State()


class AdminSupportStates(StatesGroup):
    waiting_reply = State()


bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def is_admin(uid: int) -> bool: return uid in ADMIN_IDS


async def safe_edit_app_message(message: Message, new_status_text: str, reply_markup):
    try:
        if message.photo:
            new_caption = f"{message.caption.split('Статус:')[0].strip()}\n\nСтатус: {new_status_text}"
            await message.edit_caption(caption=new_caption, reply_markup=reply_markup)
        else:
            new_text = f"{message.text.split('Статус:')[0].strip()}\n\nСтатус: {new_status_text}"
            await message.edit_text(text=new_text, reply_markup=reply_markup)
    except Exception:
        await message.reply(f"Статус: {new_status_text}", reply_markup=reply_markup)


async def get_mode_message_and_kb(mode: str):
    ops = await get_operators()

    if mode == "number":
        possible_ops = [op for op in ops if op["supports_number"]]
        field = "number_active"
    else:
        possible_ops = [op for op in ops if op["supports_qr"]]
        field = "qr_active"

    active_ops = [op for op in possible_ops if op[field]]
    inactive_ops = [op for op in possible_ops if not op[field]]

    if not active_ops:
        if mode == "number":
            text = f"{E_NOT_ACCEPT_HTML} <b>Приём операторов сейчас закрыт</b>\n\nЗаглядывайте позже — как только приём откроют, кнопки снова заработают."
        else:
            text = f"{E_NOT_ACCEPT_HTML} <b>Готовые QR сейчас не принимаются</b>\n\nГотовые QR принимаются с 04:00 до 21:00 МСК. Приходите в 04:00. Или сдайте номер."
    else:
        text = f"{E_PHONE_HTML} <b>Выберите оператора:</b>"
        if inactive_ops:
            inactive_names = ", ".join([op['name'] for op in inactive_ops])
            text += f"\n\n{E_NOT_ACCEPT_HTML} <b>Сейчас не принимаются:</b> {inactive_names}"

    return text, operators_kb(possible_ops, mode, 'regular')


@dp.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    referrer_id = None
    parts = msg.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            ref = int(parts[1][4:])
            if ref != msg.from_user.id: referrer_id = ref
        except ValueError:
            pass

    await create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name, referrer_id)

    try:
        m = await msg.bot.get_chat_member(CHANNEL_ID, msg.from_user.id)
        subscribed = m.status not in ("left", "kicked")
    except Exception:
        subscribed = False

    if subscribed:
        await msg.answer(f"{E_GREETING_HTML} Привет, <b>{msg.from_user.full_name}</b>!\n\nМеню ниже {E_DOWN_HTML}",
                         reply_markup=main_menu_kb(is_admin(msg.from_user.id)))
    else:
        await msg.answer(
            f"{E_GREETING_HTML} Привет, <b>{msg.from_user.full_name}</b>!\n\nДля начала подпишись на канал.",
            reply_markup=sub_kb())


@dp.callback_query(F.data == "check_sub")
async def check_sub(cb: CallbackQuery):
    try:
        m = await cb.bot.get_chat_member(CHANNEL_ID, cb.from_user.id)
        ok = m.status not in ("left", "kicked")
    except Exception:
        ok = False

    if not ok: return await cb.answer("❌ Подписка не найдена.", show_alert=True)
    await cb.message.edit_text(f"{E_SUCCESS_HTML} Подписка подтверждена!")
    await cb.message.answer("Добро пожаловать!", reply_markup=main_menu_kb(is_admin(cb.from_user.id)))
    await cb.answer()


# --- ПРОФИЛЬ ---
@dp.message(F.text.contains("Мой профиль"))
async def profile(msg: Message):
    u = await get_user(msg.from_user.id)
    if not u: return await msg.answer("Нажми /start.")

    pending = await pending_amount(msg.from_user.id)
    available = u['balance']
    withdrawn = await get_total_withdrawn(msg.from_user.id)
    total_earned = available + pending + withdrawn

    created_raw = u['created_at']
    try:
        created_dt = datetime.strptime(created_raw.split('.')[0], "%Y-%m-%d %H:%M:%S")
        days_with_us = (datetime.utcnow() - created_dt).days + 1
        created_str = created_dt.strftime("%d.%m.%Y")
    except:
        days_with_us = 1
        created_str = "01.01.2024"

    text = (
        f"{E_PROFILE_HTML} <b>Мой профиль</b>\n\n"
        f"{E_WALLET_HTML} <b>Баланс:</b> <b>${total_earned:.2f}</b>\n"
        f"├ Доступно к выводу: <b>${available:.2f}</b>\n"
        f"├ На проверке: <b>${pending:.2f}</b>\n"
        f"└ Выведено: <b>${withdrawn:.2f}</b>\n\n"
        f"{E_STATS_HTML} <b>Статистика:</b>\n"
        f"{E_SUCCESS_HTML} Успешно: <b>{u['successful_orders']}</b>\n"
        f"{E_FAIL_HTML} Неуспешно: <b>{u['failed_orders']}</b>\n"
        f"{E_TOTAL_HTML} Всего: <b>{u['successful_orders'] + u['failed_orders']}</b>\n\n"
        f"{E_CALENDAR_HTML} С нами с {created_str} ({days_with_us} дн.)"
    )

    await msg.answer(text, reply_markup=profile_kb(), disable_web_page_preview=True)


# --- ИСТОРИЯ И ЖУРНАЛ ---
@dp.callback_query(F.data == "audit_log")
async def audit_log(cb: CallbackQuery):
    apps = await get_user_applications(cb.from_user.id)
    if not apps:
        return await cb.answer("У вас пока нет заявок.", show_alert=True)

    text = f"{E_ORDER_HTML} <b>Журнал заявок (последние 10):</b>\n\n"
    for a in apps:
        status = {"pending": "⏳ В ожидании", "accepted": "✅ Принято", "rejected": "❌ Отклонено"}.get(a['status'],
                                                                                                     a['status'])
        val = a['phone_number'] if a['mode'] == 'number' else a['qr_number']
        text += f"<b>#{a['id']}</b> | {a['mode'].upper()} | {val}\nСтатус: {status}\n\n"

    await cb.message.answer(text)
    await cb.answer()


@dp.callback_query(F.data == "withdraw_history")
async def withdraw_history(cb: CallbackQuery):
    wds = await get_user_withdrawals(cb.from_user.id)
    if not wds:
        return await cb.answer("У вас пока нет выплат.", show_alert=True)

    text = f"{E_MONEY_HTML} <b>История выплат:</b>\n\n"
    for w in wds:
        status = "✅ Выплачено" if w['status'] == 'completed' else "⏳ В обработке"
        date = w['created_at'].split('.')[0]
        text += f"<b>#{w['id']}</b> | ${w['amount']:.2f}\nДата: {date}\nСтатус: {status}\n\n"

    await cb.message.answer(text)
    await cb.answer()


# --- ПОДДЕРЖКА ---
@dp.message(F.text.contains("Поддержка"))
async def support_btn(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(f"{E_SUPPORT_HTML} <b>Поддержка</b>\n\nВыберите действие:", reply_markup=support_menu_kb())


@dp.callback_query(F.data == "support_new")
async def support_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SupportStates.waiting_msg)
    await cb.message.edit_text("📝 Опишите вашу проблему в одном сообщении. Администратор ответит вам прямо здесь.")
    await cb.answer()


@dp.message(SupportStates.waiting_msg)
async def handle_support_msg(msg: Message, state: FSMContext):
    await state.clear()
    t_id = await create_ticket(msg.from_user.id, msg.html_text or "Фото/Медиа")

    admin_msg = f"🎫 <b>Обращение #{t_id}</b>\n\n👤 <b>От:</b> {msg.from_user.full_name}\n{E_LINK_HTML} @{msg.from_user.username or '—'}\n🆔 <code>{msg.from_user.id}</code>\n\n💬 <b>Сообщение:</b>\n{msg.html_text}"

    if msg.photo:
        await bot.send_photo(ADMIN_GROUP_ID, msg.photo[-1].file_id, caption=admin_msg,
                             reply_markup=admin_ticket_action_kb(t_id))
    else:
        await bot.send_message(ADMIN_GROUP_ID, admin_msg, reply_markup=admin_ticket_action_kb(t_id))

    await msg.answer(f"{E_SUCCESS_HTML} Обращение #{t_id} создано. Ожидайте ответа.",
                     reply_markup=user_ticket_action_kb(t_id))


@dp.callback_query(F.data == "support_my")
async def support_my(cb: CallbackQuery):
    tickets = await get_user_tickets(cb.from_user.id)
    if not tickets:
        return await cb.answer("У вас пока нет обращений.", show_alert=True)

    for t in tickets:
        status_text = "✅ Закрыто" if t['status'] == 'closed' else "⏳ В ожидании"
        text = f"📁 <b>Обращение #{t['id']}</b> ({status_text})\n\n"
        if t['reply']:
            text += f"<i>Ответ: {t['reply']}</i>\n"

        kb = user_ticket_action_kb(t['id']) if t['status'] != 'closed' else None
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()


# --- ОТВЕТЫ И ЗАКРЫТИЕ ТИКЕТОВ ---
@dp.callback_query(F.data.startswith("user_reply_ticket:"))
async def user_reply_ticket(cb: CallbackQuery, state: FSMContext):
    t_id = int(cb.data.split(":")[1])
    await state.set_state(SupportStates.waiting_reply)
    await state.update_data(ticket_id=t_id)
    await cb.message.reply("✍️ Напишите ваш ответ:")
    await cb.answer()


@dp.message(SupportStates.waiting_reply)
async def user_send_reply(msg: Message, state: FSMContext):
    data = await state.get_data()
    t_id = data.get("ticket_id")
    await state.clear()

    admin_msg = f"🎫 <b>Обращение #{t_id} (Ответ юзера)</b>\n\n👤 <b>От:</b> {msg.from_user.full_name}\n🆔 <code>{msg.from_user.id}</code>\n\n💬 <b>Сообщение:</b>\n{msg.html_text}"

    if msg.photo:
        await bot.send_photo(ADMIN_GROUP_ID, msg.photo[-1].file_id, caption=admin_msg,
                             reply_markup=admin_ticket_action_kb(t_id))
    else:
        await bot.send_message(ADMIN_GROUP_ID, admin_msg, reply_markup=admin_ticket_action_kb(t_id))

    await msg.answer(f"{E_SUCCESS_HTML} Ваш ответ отправлен.", reply_markup=user_ticket_action_kb(t_id))


@dp.callback_query(F.data.startswith("user_close_ticket:"))
async def user_close_ticket(cb: CallbackQuery):
    t_id = int(cb.data.split(":")[1])
    await reply_ticket(t_id, "Пользователь отметил проблему решенной")
    await cb.message.edit_text(f"{E_SUCCESS_HTML} Обращение #{t_id} закрыто. Спасибо!", reply_markup=None)
    await bot.send_message(ADMIN_GROUP_ID, f"✅ <b>Обращение #{t_id}</b> закрыто пользователем.")
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_reply_ticket:"))
async def adm_reply_ticket(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    t_id = int(cb.data.split(":")[1])
    await state.set_state(AdminSupportStates.waiting_reply)
    await state.update_data(ticket_id=t_id)
    await cb.message.reply("✍️ Введите ответ для пользователя:")
    await cb.answer()


@dp.message(AdminSupportStates.waiting_reply)
async def admin_send_reply(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    t_id = data.get("ticket_id")
    await state.clear()

    await reply_ticket(t_id, msg.html_text)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM tickets WHERE id=?", (t_id,)) as c:
            t = await c.fetchone()

    if t:
        try:
            await bot.send_message(t['user_id'], f"🎧 <b>Ответ по обращению #{t_id}:</b>\n\n{msg.html_text}",
                                   reply_markup=user_ticket_action_kb(t_id))
        except:
            pass

    await msg.answer(f"{E_SUCCESS_HTML} Ответ отправлен пользователю!")


@dp.callback_query(F.data.startswith("adm_close_ticket:"))
async def adm_close_ticket(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    t_id = int(cb.data.split(":")[1])
    await reply_ticket(t_id, "Закрыто администратором")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM tickets WHERE id=?", (t_id,)) as c:
            t = await c.fetchone()

    if t:
        try:
            await bot.send_message(t['user_id'], f"✅ <b>Обращение #{t_id} закрыто администратором.</b>")
        except:
            pass

    await cb.message.edit_text(f"✅ Обращение #{t_id} закрыто.", reply_markup=None)
    await cb.answer()


# --- ВЫВОД ---
@dp.callback_query(F.data == "withdraw")
async def withdraw(cb: CallbackQuery):
    u = await get_user(cb.from_user.id)
    amount = u["balance"]

    if amount < 5.0:
        return await cb.answer(f"❌ Минимум для вывода: $5.00\nБаланс: ${amount:.2f}", show_alert=True)

    await create_withdrawal(cb.from_user.id, amount)

    await cb.message.answer(
        f"{E_SUCCESS_HTML} Заявка на вывод <b>${amount:.2f}</b> создана!\nОжидайте выплаты (обычно в конце рабочего дня).")
    await bot.send_message(ADMIN_GROUP_ID,
                           f"💸 <b>Новая заявка на вывод!</b>\n\n👤 {cb.from_user.full_name}\n🆔 <code>{cb.from_user.id}</code>\n💰 Сумма: <b>${amount:.2f}</b>")
    await cb.answer()


# --- РАБОТА ---
@dp.message(F.text.contains("Начать работу"))
async def start_work(msg: Message, state: FSMContext):
    await state.clear()
    if await check_active_app(msg.from_user.id):
        return await msg.answer(f"{E_FAIL_HTML} У вас уже есть активная заявка на проверке. Дождитесь ее завершения.")

    await state.set_state(WorkStates.choosing_operator)
    await state.update_data(mode="number")

    text, kb = await get_mode_message_and_kb("number")
    await msg.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("mode:"))
async def choose_mode(cb: CallbackQuery, state: FSMContext):
    mode = cb.data.split(":")[1]
    await state.update_data(mode=mode)

    text, kb = await get_mode_message_and_kb(mode)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data == "back_main")
async def back_main_inline(cb: CallbackQuery):
    await cb.message.edit_text("🏠 Главное меню внизу 👇", reply_markup=None)
    await cb.answer()


@dp.callback_query(F.data.startswith("cat:"))
async def switch_category(cb: CallbackQuery):
    _, mode, category = cb.data.split(":")
    ops = await get_operators()

    if mode == "number":
        possible_ops = [op for op in ops if op["supports_number"]]
        field = "number_active"
    else:
        possible_ops = [op for op in ops if op["supports_qr"]]
        field = "qr_active"

    active_ops = [op for op in possible_ops if op[field]]
    inactive_ops = [op for op in possible_ops if not op[field]]

    text = f"{E_PHONE_HTML} <b>Выберите оператора:</b>"
    if not active_ops:
        text = f"{E_NOT_ACCEPT_HTML} <b>Приём закрыт</b>\n\nЗаглядывайте позже."
    elif inactive_ops:
        inactive_names = ", ".join([op['name'] for op in inactive_ops])
        text += f"\n\n{E_NOT_ACCEPT_HTML} <b>Сейчас не принимаются:</b> {inactive_names}"

    await cb.message.edit_text(text, reply_markup=operators_kb(possible_ops, mode, category))
    await cb.answer()


@dp.callback_query(F.data.startswith("op_disabled:"))
async def op_disabled_alert(cb: CallbackQuery):
    op_name = cb.data.split(":", 1)[1]
    await cb.answer(f"⚠️ У оператора {op_name} закрыт приём!", show_alert=True)


@dp.callback_query(F.data.startswith("op:"))
async def choose_operator(cb: CallbackQuery, state: FSMContext):
    _, mode, op_id = cb.data.split(":")
    op = await get_operator(int(op_id))
    await state.update_data(operator_id=op["id"], mode=mode)

    if mode == "number":
        await state.set_state(WorkStates.waiting_number)
        await cb.message.edit_text(
            f"{E_PHONE_HTML} <b>{op['name']}</b>\n{E_MONEY_HTML} ${op['price_number']:.2f}\n\nОтправь <b>номер</b> (+79XXXXXXXXX):")
    else:
        await state.set_state(WorkStates.waiting_qr_photo)
        await cb.message.edit_text(
            f"🖼 <b>{op['name']}</b>\n{E_MONEY_HTML} ${op['price_qr']:.2f}\n\n📸 <b>Шаг 1/2:</b> отправь <b>фото QR-кода</b>:")
    await cb.answer()


# --- ПРИЕМ НОМЕРА ---
@dp.message(WorkStates.waiting_number, F.text)
async def receive_number(msg: Message, state: FSMContext):
    if not PHONE_REGEX.match(msg.text.strip()):
        return await msg.answer("❗ Формат: <code>+79187382031</code>")

    phone = msg.text.strip()

    if await check_number_already_accepted("number", phone):
        return await msg.answer(f"{E_FAIL_HTML} Этот номер уже был сдан и оплачен. Нельзя сдавать повторно.")

    data = await state.get_data()
    op = await get_operator(data["operator_id"])
    app_id = await create_application(user_id=msg.from_user.id, operator_id=op["id"], mode="number", phone_number=phone)

    text = (f"🆕 <b>Заявка #{app_id}</b> [{E_PHONE_HTML} Номер]\n\n"
            f"{E_PROFILE_HTML} {msg.from_user.full_name}\n{E_LINK_HTML} @{msg.from_user.username or '—'}\n🆔 <code>{msg.from_user.id}</code>\n\n"
            f"{E_PHONE_HTML} Оператор: <b>{op['name']}</b>\n☎️ Номер: <code>{phone}</code>\n{E_MONEY_HTML} Цена: ${op['price_number']:.2f}")

    sent = await bot.send_message(ADMIN_GROUP_ID, text, reply_markup=application_admin_kb(app_id, "number"))
    await set_admin_message(app_id, ADMIN_GROUP_ID, sent.message_id)
    await state.clear()
    await msg.answer(
        f"{E_SUCCESS_HTML} <b>Заявка успешно отправлена на проверку!</b>\nОжидайте решения администратора.")


# --- ПРИЕМ QR ---
@dp.message(WorkStates.waiting_qr_photo, F.photo)
async def qr_photo(msg: Message, state: FSMContext):
    await state.update_data(qr_photo_id=msg.photo[-1].file_id)
    await state.set_state(WorkStates.waiting_qr_number)
    await msg.answer(
        f"{E_SUCCESS_HTML} Фото получено.\n\n{E_PHONE_HTML} <b>Шаг 2/2:</b> отправь <b>номер от QR</b> (+79XXXXXXXXX):")


@dp.message(WorkStates.waiting_qr_photo)
async def qr_photo_bad(msg: Message):
    await msg.answer("❗ Отправь именно <b>фото</b>.")


@dp.message(WorkStates.waiting_qr_number, F.text)
async def qr_number(msg: Message, state: FSMContext):
    if not PHONE_REGEX.match(msg.text.strip()):
        return await msg.answer("❗ Формат: <code>+79187382031</code>")

    qr_num = msg.text.strip()

    if await check_number_already_accepted("qr", qr_num):
        return await msg.answer(f"{E_FAIL_HTML} Этот QR уже был сдан и оплачен. Нельзя сдавать повторно.")

    data = await state.get_data()
    op = await get_operator(data["operator_id"])
    app_id = await create_application(user_id=msg.from_user.id, operator_id=op["id"], mode="qr",
                                      qr_photo_id=data["qr_photo_id"], qr_number=qr_num)

    caption = (f"🆕 <b>Заявка #{app_id}</b> [🖼 QR]\n\n"
               f"{E_PROFILE_HTML} {msg.from_user.full_name}\n{E_LINK_HTML} @{msg.from_user.username or '—'}\n🆔 <code>{msg.from_user.id}</code>\n\n"
               f"{E_PHONE_HTML} Оператор: <b>{op['name']}</b>\n🔢 Номер QR: <code>{qr_num}</code>\n{E_MONEY_HTML} Цена: ${op['price_qr']:.2f}")
    sent = await bot.send_photo(ADMIN_GROUP_ID, photo=data["qr_photo_id"], caption=caption,
                                reply_markup=application_admin_kb(app_id, "qr"))
    await set_admin_message(app_id, ADMIN_GROUP_ID, sent.message_id)
    await state.clear()
    await msg.answer(
        f"{E_SUCCESS_HTML} <b>Заявка успешно отправлена на проверку!</b>\nОжидайте решения администратора.")


# --- КОД ОТ ЮЗЕРА ---
@dp.callback_query(F.data == "user_write_code")
async def user_write_code(cb: CallbackQuery, state: FSMContext):
    await state.set_state(WorkStates.waiting_code)
    await cb.message.edit_text("⌨️ Отправь код одним сообщением:")
    await cb.answer()


@dp.callback_query(F.data == "user_cancel_code")
async def user_cancel_code(cb: CallbackQuery):
    app = await get_app_awaiting_code(cb.from_user.id)
    if app:
        await update_app(app["id"], status="cancelled", awaiting_code=0)
        await bot.send_message(ADMIN_GROUP_ID, f"⏹ <b>Пользователь отменил запрос кода для заявки #{app['id']}.</b>")
    await cb.message.edit_text("❌ Вы отменили запрос кода. Заявка отменена.")
    await cb.answer()


@dp.message(WorkStates.waiting_code, F.text)
async def catch_code(msg: Message, state: FSMContext):
    app = await get_app_awaiting_code(msg.from_user.id)
    if not app:
        await state.clear()
        return await msg.answer("⚠️ Активная заявка не найдена.")

    await update_app(app["id"], code=msg.text.strip(), status="code_sent", awaiting_code=0)
    await bot.send_message(ADMIN_GROUP_ID, f"💬 <b>Код для заявки #{app['id']}:</b>\n<code>{msg.text.strip()}</code>")
    await state.clear()
    await msg.answer(f"{E_SUCCESS_HTML} Код отправлен администратору.")


# --- АДМИН-ПАНЕЛЬ ---
@dp.message(F.text.contains("Админ-панель"))
async def panel_msg(msg: Message, state: FSMContext):
    await state.clear()
    if not is_admin(msg.from_user.id):
        return await msg.answer(f"⛔ У вас нет доступа.\nВаш ID: <code>{msg.from_user.id}</code>")
    await msg.answer("👑 <b>Админ-панель</b>", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "admin_panel")
async def back_to_admin(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text("👑 <b>Админ-панель</b>", reply_markup=admin_panel_kb())
    await cb.answer()


@dp.callback_query(F.data == "close_admin")
async def close_admin(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text(
        "👑 <b>Админ-панель закрыта.</b>\nНажми на кнопку «👑 Админ-панель» внизу, чтобы открыть её снова.",
        reply_markup=None)
    await cb.answer()


# --- ВЫВОДЫ (АДМИН) ---
@dp.callback_query(F.data == "adm_withdrawals")
async def adm_withdrawals(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    ws = await get_pending_withdrawals()
    if not ws:
        return await cb.answer("Нет активных заявок на вывод.", show_alert=True)
    await cb.message.edit_text("💸 <b>Заявки на вывод</b>\n\nНажмите на заявку, чтобы отметить её как выплаченную:",
                               reply_markup=adm_withdrawals_kb(ws))
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_pay_w:"))
async def adm_pay_w(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    w_id = int(cb.data.split(":")[1])

    ws = await get_pending_withdrawals()
    w = next((x for x in ws if x['id'] == w_id), None)
    if not w:
        return await cb.answer("Заявка не найдена или уже выплачена.", show_alert=True)

    amount = w['amount']
    user_id = w['user_id']

    try:
        crypto_bal = await get_crypto_balance()
    except Exception as e:
        return await cb.answer(f"⚠️ Ошибка подключения к CryptoPay:\n{e}", show_alert=True)

    if crypto_bal < amount:
        return await cb.answer(
            f"❌ Недостаточно средств на CryptoPay!\n\n"
            f"Требуется: ${amount:.2f}\n"
            f"В наличии: ${crypto_bal:.2f}\n\n"
            f"Пополните баланс в @CryptoBot и нажмите снова.",
            show_alert=True
        )

    try:
        link = await create_check(amount, user_id)
    except Exception as e:
        return await cb.answer(f"⚠️ Ошибка при создании чека: {e}", show_alert=True)

    try:
        await bot.send_message(
            user_id,
            f"💸 <b>Ваша выплата готова!</b>\n\n"
            f"Сумма: <b>${amount:.2f}</b>\n"
            f"Ссылка на получение: {link}\n\n"
            f"Активируйте чек в @CryptoBot."
        )
    except Exception:
        await cb.message.answer(f"⚠️ Не удалось написать юзеру {user_id}, но чек создан: {link}")

    await approve_withdrawal(w_id)
    await cb.answer("Выплата успешно отправлена юзеру!", show_alert=True)

    ws = await get_pending_withdrawals()
    if not ws:
        await cb.message.edit_text("💸 <b>Все заявки на вывод обработаны!</b>", reply_markup=admin_panel_kb())
    else:
        await cb.message.edit_reply_markup(reply_markup=adm_withdrawals_kb(ws))


@dp.callback_query(F.data == "adm_manage_ops")
async def adm_manage_ops(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    ops = await get_operators()
    await cb.message.edit_text("⚙️ Выберите оператора для вкл/выкл:", reply_markup=adm_ops_list_kb(ops))
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_op:"))
async def op_edit(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    op = await get_operator(int(cb.data.split(":")[1]))
    await cb.message.edit_text(
        f"⚙️ <b>{op['name']}</b>\n\n{E_PHONE_HTML} Номер: {'🟢 вкл' if op['number_active'] else '🔴 выкл'}\n🖼 QR: {'🟢 вкл' if op['qr_active'] else '🔴 выкл'}",
        reply_markup=operator_edit_kb(op))
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_change_name:"))
async def op_change_name(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    op_id = int(cb.data.split(":")[1])
    await state.set_state(AdminStates.waiting_new_name)
    await state.update_data(op_id=op_id)
    await cb.message.answer(f"✏️ Введи <b>новое название</b> для этого оператора:")
    await cb.answer()


@dp.message(AdminStates.waiting_new_name)
async def save_new_name(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    if not msg.text: return await msg.answer("❗ Название не может быть пустым.")
    data = await state.get_data()
    op_id = data["op_id"]
    await update_operator_name(op_id, msg.text.strip())
    await state.clear()
    op = await get_operator(op_id)
    await msg.answer(f"{E_SUCCESS_HTML} Название изменено на <b>{msg.text.strip()}</b>!",
                     reply_markup=operator_edit_kb(op))


@dp.callback_query(F.data.startswith("adm_tog:"))
async def op_toggle(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    _, op_id, field = cb.data.split(":")
    await toggle_operator(int(op_id), field)
    await cb.message.edit_reply_markup(reply_markup=operator_edit_kb(await get_operator(int(op_id))))
    await cb.answer("Изменено")


@dp.callback_query(F.data == "adm_start_all")
async def adm_start_all(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await start_all_operators()
    await cb.answer("Все операторы включены (Начало ворка)!", show_alert=True)
    await cb.message.edit_text("👑 <b>Админ-панель</b>\n\n✅ <i>Все операторы включены!</i>",
                               reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "adm_stop_all")
async def adm_stop_all(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await stop_all_operators()
    await cb.answer("Все операторы выключены (Стоп-ворк)!", show_alert=True)
    await cb.message.edit_text("👑 <b>Админ-панель</b>\n\n⏹ <i>Все операторы выключены!</i>",
                               reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "adm_run_payouts")
async def adm_run_payouts(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.answer("Запускаю выплаты...", show_alert=True)
    payouts = await get_all_pending_payouts()
    count = 0
    for app in payouts:
        if not await try_payout(app["id"]): continue
        op = await get_operator(app["operator_id"])
        price = op["price_qr"] if app["mode"] == "qr" else op["price_number"]
        await add_balance(app["user_id"], price)
        try:
            await bot.send_message(app["user_id"],
                                   f"{E_SUCCESS_HTML} <b>Материал засчитан</b>\n\n{E_PHONE_HTML} Номер: <code>{app['qr_number']}</code>\n{E_ORDER_HTML} Заказ: <b>#{app['id']}</b>\n\nОфис принял материал, замечаний нет. Выплата переведена в доступно к выводу.")
        except Exception:
            pass
        count += 1
    await cb.message.answer(f"{E_SUCCESS_HTML} Выплаты завершены. Начислено заявок: <b>{count}</b>")


@dp.callback_query(F.data == "adm_change_price_mode")
async def adm_change_price_mode(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text(f"{E_MONEY_HTML} Выберите категорию для смены цены:", reply_markup=adm_price_mode_kb())
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_price_mode:"))
async def adm_price_mode(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    mode = cb.data.split(":")[1]
    ops = await get_operators()
    await cb.message.edit_text(f"{E_MONEY_HTML} Выберите оператора:", reply_markup=adm_price_ops_kb(ops, mode))
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_price_op:"))
async def adm_price_op(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    _, op_id, mode = cb.data.split(":")
    await state.set_state(AdminStates.waiting_price)
    await state.update_data(op_id=int(op_id), mode=mode)
    await cb.message.answer(f"Введи новую цену для режима <b>{'Номер' if mode == 'number' else 'QR'}</b>:")
    await cb.answer()


@dp.message(AdminStates.waiting_price)
async def save_price(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    try:
        price = float(msg.text.replace(",", "."))
    except:
        return await msg.answer("❗ Некорректная цена.")
    data = await state.get_data()
    field = "price_number" if data["mode"] == "number" else "price_qr"
    await update_operator_price(data["op_id"], field, price)
    await state.clear()
    op = await get_operator(data["op_id"])
    await msg.answer(f"{E_SUCCESS_HTML} Сохранено. Новая цена для {op['name']} ({data['mode']}): <b>${price:.2f}</b>",
                     reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "adm_stats_menu")
async def adm_stats_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text(f"{E_STATS_HTML} <b>Статистика</b>", reply_markup=adm_stats_menu_kb())
    await cb.answer()


@dp.callback_query(F.data == "adm_stats_day")
async def stats_day(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    ok, fail, total = await stats_today()
    await cb.message.answer(
        f"{E_CALENDAR_HTML} <b>За сегодня</b>\n\n{E_SUCCESS_HTML} Успешных: <b>{ok}</b>\n{E_FAIL_HTML} Неуспешных: <b>{fail}</b>\n{E_MONEY_HTML} Сумма: <b>${total:.2f}</b>")
    await cb.answer()


@dp.callback_query(F.data == "adm_stats_total")
async def stats_total_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    users, balance, apps = await stats_total()
    await cb.message.answer(
        f"{E_TOTAL_HTML} <b>Всего</b>\n\n👥 Юзеров: <b>{users}</b>\n{E_WALLET_HTML} Баланс: <b>${balance:.2f}</b>\n{E_ORDER_HTML} Заявок: <b>{apps}</b>")
    await cb.answer()


@dp.callback_query(F.data == "adm_broadcast")
async def broadcast_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.set_state(AdminStates.waiting_broadcast)
    await cb.message.answer(f"{E_BROADCAST_HTML} Отправь сообщение для рассылки:")
    await cb.answer()


@dp.message(AdminStates.waiting_broadcast)
async def do_broadcast(msg: Message, state: FSMContext):
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
    await msg.answer(f"{E_SUCCESS_HTML} Доставлено: {sent}")


# --- РЕШЕНИЯ ПО ЗАЯВКАМ ---
@dp.callback_query(F.data.startswith("adm_accept:"))
async def accept(cb: CallbackQuery):
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
            await bot.send_message(app["user_id"],
                                   f"{E_SUCCESS_HTML} <b>Заявка #{app_id} принята!</b>\n{E_MONEY_HTML} +${price:.2f}")
        except:
            pass
    else:
        payout_at = (datetime.utcnow() + timedelta(minutes=QR_COOLDOWN_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
        await update_app(app_id, status="accepted", awaiting_code=0, payout_at=payout_at,
                         processed_at=datetime.utcnow())
        try:
            await bot.send_message(app["user_id"],
                                   f"{E_NUM_ACCEPTED_HTML} <b>Номер принят в работу</b>\n\n{E_PHONE_HTML} Номер: <code>{app['qr_number']}</code>\n{E_ORDER_HTML} Заказ: <b>#{app_id}</b>\n\nОфис взял QR в работу.")
        except:
            pass

    await increment_orders(app["user_id"], True)
    u = await get_user(app["user_id"])
    if u and u["referrer_id"]:
        await add_balance(u["referrer_id"], REF_BONUS)
        try:
            await bot.send_message(u["referrer_id"], f"🎁 Реф. бонус: <b>+${REF_BONUS:.2f}</b>")
        except:
            pass

    await safe_edit_app_message(cb.message, f"{E_SUCCESS_HTML} ПРИНЯТА",
                                application_admin_kb(app_id, app["mode"], "accepted"))
    await cb.answer("Принято")


# --- ОТМЕНА ПРИНЯТИЯ ---
@dp.callback_query(F.data.startswith("adm_undo_accept:"))
async def undo_accept(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    if app["status"] != 'accepted': return await cb.answer("Нельзя отменить", show_alert=True)

    op = await get_operator(app["operator_id"])
    price = op["price_number"] if app["mode"] == "number" else op["price_qr"]

    u = await get_user(app["user_id"])
    deduct = min(price, max(0.0, u["balance"] if u else 0.0))
    if deduct > 0:
        await add_balance(app["user_id"], -deduct)

    await update_app(app_id, status="pending", payout_at=None, processed_at=None)
    await increment_orders(app["user_id"], True, -1)

    try:
        await bot.send_message(app["user_id"],
                               f"⚠️ <b>Заявка #{app_id} возвращена на проверку.</b>\nСписано: ${deduct:.2f}")
    except:
        pass

    await safe_edit_app_message(cb.message, f"🔄 ВОЗВРАЩЕНА", application_admin_kb(app_id, app["mode"], "pending"))
    await cb.answer("Возвращено")


@dp.callback_query(F.data.startswith("adm_cancel:"))
async def cancel_app(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    if not app or app["status"] != 'pending': return await cb.answer("Уже обработано", show_alert=True)

    await update_app(app_id, status="cancelled", processed_at=datetime.utcnow())
    try:
        await bot.send_message(app["user_id"], f"⏹ <b>Заявка #{app_id} отменена.</b>")
    except:
        pass

    await safe_edit_app_message(cb.message, f"⏹ ОТМЕНЕНА", application_admin_kb(app_id, app["mode"], "cancelled"))
    await cb.answer("Отменено")


@dp.callback_query(F.data.startswith("adm_code:"))
async def request_code(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    await update_app(app_id, status="code_requested", awaiting_code=1)

    try:
        await bot.send_message(
            app["user_id"],
            f"💬 Админ запросил <b>код</b> для заявки #{app_id}.\n\n"
            f"Пожалуйста, отправь код одним сообщением.",
            reply_markup=user_code_kb()
        )
    except:
        return await cb.answer("Юзер заблокировал бота", show_alert=True)

    await safe_edit_app_message(cb.message, "💬 ЗАПРОШЕН КОД",
                                application_admin_kb(app_id, app["mode"], "code_requested"))
    await cb.answer("Запрос отправлен")


@dp.callback_query(F.data.startswith("adm_reject:"))
async def reject(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)

    if app["mode"] == "number":
        await state.set_state(AdminStates.waiting_reject_reason)
        await state.update_data(reject_app_id=app_id)
        await cb.message.answer(f"✍️ Введи <b>причину</b> для заявки #{app_id}:")
        await cb.answer()
    else:
        await cb.message.edit_reply_markup(reply_markup=reject_reason_kb(app_id))
        await cb.answer("Выбери причину")


@dp.message(AdminStates.waiting_reject_reason)
async def process_reject_reason(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    app_id = data.get("reject_app_id")
    await state.clear()
    if not app_id or not msg.text: return await msg.answer("⚠️ Пустая причина.")

    app = await get_application(int(app_id))
    if not app or app["status"] in ("rejected", "accepted", "cancelled"): return

    await update_app(app_id, status="rejected", awaiting_code=0, reject_reason=msg.text.strip(),
                     processed_at=datetime.utcnow())
    await increment_orders(app["user_id"], False)
    try:
        await bot.send_message(app["user_id"],
                               f"{E_FAIL_HTML} <b>Заявка #{app_id} отклонена.</b>\n\n<b>Причина:</b> {msg.text.strip()}")
    except:
        pass

    # Чтобы не было дубля кнопок, отправляем новое сообщение-ответ
    await msg.answer(f"{E_FAIL_HTML} Заявка #{app_id} отклонена.")


@dp.callback_query(F.data.startswith("adm_back:"))
async def reject_back(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    await cb.message.edit_reply_markup(reply_markup=application_admin_kb(app_id, app["mode"], app["status"]))
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_reason:"))
async def reject_with_reason(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    _, app_id, reason = cb.data.split(":")
    app_id = int(app_id)
    app = await get_application(app_id)
    if not app or app["status"] in ("rejected", "accepted", "cancelled"): return

    await update_app(app_id, status="rejected", awaiting_code=0, reject_reason=reason, processed_at=datetime.utcnow())
    await increment_orders(app["user_id"], False)

    op = await get_operator(app["operator_id"])
    phone = app["qr_number"]

    if reason == "block":
        u = await get_user(app["user_id"])
        fine = min(op["price_qr"], max(0.0, u["balance"] if u else 0.0))
        if fine > 0: await add_balance(app["user_id"], -fine)
        msg_text = f"{E_BLOCK_HTML} <b>Ваш номер {phone} заблокирован.</b>\nС баланса списано <b>${fine:.2f}</b>."
        try:
            await bot.send_message(app["user_id"], msg_text)
        except:
            pass
    elif reason == "slet":
        try:
            await bot.send_message(app["user_id"], f"{E_FAIL_HTML} <b>Ваш номер {phone} - Не скан.</b>")
        except:
            pass

    reason_lbl = {"block": "Блок", "slet": "Не скан"}.get(reason, reason)
    await safe_edit_app_message(cb.message, f"{E_FAIL_HTML} ОТКЛОНЕНА ({reason_lbl})",
                                application_admin_kb(app_id, app["mode"], "rejected"))
    await cb.answer("Отклонено")


async def payout_worker():
    while True:
        try:
            for app in await pending_payouts():
                if not await try_payout(app["id"]): continue
                op = await get_operator(app["operator_id"])
                price = op["price_qr"] if app["mode"] == "qr" else op["price_number"]
                await add_balance(app["user_id"], price)
                try:
                    await bot.send_message(app["user_id"],
                                           f"{E_SUCCESS_HTML} <b>Материал засчитан</b>\n\n{E_PHONE_HTML} Номер: <code>{app['qr_number']}</code>\n{E_ORDER_HTML} Заказ: <b>#{app['id']}</b>\n\nОфис принял материал, замечаний нет. Выплата переведена в доступно к выводу.")
                except Exception:
                    pass
        except Exception:
            logging.exception("payout_worker error")
        await asyncio.sleep(30)


async def work_scheduler():
    while True:
        try:
            now_utc = datetime.utcnow()
            now_msk = now_utc + timedelta(hours=3)

            if 6 <= now_msk.hour < 19:
                ops = await get_operators()
                if not any(op["number_active"] or op["qr_active"] for op in ops):
                    await start_all_operators()
                    logging.info("Авто-ворк: операторы включены (06:00+)")
            else:
                ops = await get_operators()
                if any(op["number_active"] or op["qr_active"] for op in ops):
                    await stop_all_operators()
                    logging.info("Авто-ворк: операторы выключены (19:00+)")
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
    logging.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())