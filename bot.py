import asyncio, logging, re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart, StateFilter
from aiogram.dispatcher.event.bases import SkipHandler

from config import (BOT_TOKEN, ADMIN_IDS, ADMIN_GROUP_ID, REF_BONUS,
                    QR_COOLDOWN_MINUTES, ALLOWED_PREFIXES, ENABLE_REGION_FILTER)
from database import *
from keyboards import *
from middlewares.subscription import SubscriptionMiddleware
from cryptobot import get_crypto_balance, create_check

# --- HTML ЭМОДЗИ ДЛЯ ТЕКСТА ---
E_GREETING_HTML = '<tg-emoji emoji-id="5258501105293205250">👋</tg-emoji>'
E_START_WORK_HTML = '<tg-emoji emoji-id="5258337316715373336">📞</tg-emoji>'
E_PROFILE_HTML = '<tg-emoji emoji-id="5879770735999717115">👤</tg-emoji>'
E_SUPPORT_HTML = '<tg-emoji emoji-id="5316727448644103237">🎧</tg-emoji>'
E_WALLET_HTML = '<tg-emoji emoji-id="5258204546391351475">💳</tg-emoji>'
E_STATS_HTML = '<tg-emoji emoji-id="5258330865674494479">📊</tg-emoji>'
E_SUCCESS_HTML = '<tg-emoji emoji-id="5776375003280838798">✅</tg-emoji>'
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
E_SETTINGS_HTML = '<tg-emoji emoji-id="6021582331251268218">⚙</tg-emoji>'
E_TIME_HTML = '<tg-emoji emoji-id="6034898821517940846">⏰</tg-emoji>'
E_HISTORY_HTML = '<tg-emoji emoji-id="6021454607513819417">📜</tg-emoji>'


# --- СОСТОЯНИЯ ---
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


class SupportStates(StatesGroup):
    waiting_msg = State()
    waiting_reply = State()


class AdminSupportStates(StatesGroup):
    waiting_reply = State()


bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def is_admin(uid: int) -> bool: return uid in ADMIN_IDS


# --- ФИКС ССЫЛКИ ---
def normalize_link(link: str) -> str:
    if not link: return "https://t.me/telegram"
    link = link.strip()
    if link.startswith("http://") or link.startswith("https://"):
        return link
    if link.startswith("@"): link = link[1:]
    return f"https://t.me/{link}"


# --- ВСПОМОГАТЕЛЬНЫЕ ---
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
        text = f"{E_NOT_ACCEPT_HTML} <b>Приём операторов сейчас закрыт</b>\n\nЗаглядывайте позже." if mode == "number" else f"{E_NOT_ACCEPT_HTML} <b>Готовые QR сейчас не принимаются</b>\n\nПриходите в 04:00. Или сдайте номер."
    else:
        text = f"{E_PHONE_HTML} <b>Выберите оператора:</b>"
        if inactive_ops:
            inactive_names = ", ".join([op['name'] for op in inactive_ops])
            text += f"\n\n{E_NOT_ACCEPT_HTML} <b>Сейчас не принимаются:</b> {inactive_names}"
    return text, operators_kb(possible_ops, mode, 'regular')


# --- СТАРТ ---
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

    await msg.answer(f"{E_GREETING_HTML} Привет, <b>{msg.from_user.full_name}</b>!\n\nМеню ниже {E_DOWN_HTML}",
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
        f"{E_PROFILE_HTML} <b>Мой профиль</b>\n\n"
        f"{E_WALLET_HTML} <b>Заработано:</b> <b>${total_earned:.2f}</b>\n"
        f"├ Доступно к выводу: <b>${available:.2f}</b>\n"
        f"├ На проверке: <b>${pending:.2f}</b>\n"
        f"├ На выводе: <b>${pending_wd:.2f}</b>\n"
        f"├ Выведено: <b>${withdrawn:.2f}</b>\n"
        f"└ Штрафы (блоки): <b>${fines:.2f}</b>\n\n"
        f"{E_STATS_HTML} <b>Статистика:</b>\n"
        f"{E_SUCCESS_HTML} Успешно: <b>{u['successful_orders']}</b>\n"
        f"{E_FAIL_HTML} Неуспешно: <b>{u['failed_orders']}</b>\n"
        f"{E_TOTAL_HTML} Всего: <b>{u['successful_orders'] + u['failed_orders']}</b>"
    )
    await msg.answer(text, reply_markup=profile_kb())


@dp.callback_query(F.data == "withdraw_history")
async def withdraw_history(cb: CallbackQuery):
    wds = await get_user_withdrawals(cb.from_user.id)
    if not wds:
        return await cb.answer("У вас пока нет выплат.", show_alert=True)

    text = f"{E_HISTORY_HTML} <b>История выплат:</b>\n\n"
    has_kb = False
    kb = InlineKeyboardBuilder()

    for w in wds:
        if w['status'] == 'completed':
            date = w['created_at'].strftime("%d.%m %H:%M")
            text += f"{E_SUCCESS_HTML} <b>${w['amount']:.2f}</b> — выплачено {date}\n"
            if w['check_url']:
                kb.button(text=f"Чек на ${w['amount']:.2f}", url=w['check_url'], icon_custom_emoji_id=E_LINK)
                has_kb = True
        elif w['status'] == 'pending':
            text += f"⏳ <b>${w['amount']:.2f}</b> — в обработке\n"
        elif w['status'] == 'cancelled':
            text += f"{E_FAIL_HTML} <b>${w['amount']:.2f}</b> — отменено ({w['reject_reason']})\n"

    if has_kb:
        await cb.message.answer(text, reply_markup=kb.as_markup())
    else:
        await cb.message.answer(text)
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
    await cb.message.answer(f"{E_SUCCESS_HTML} Заявка на вывод <b>${amount:.2f}</b> создана!\nОжидайте выплаты.")
    await bot.send_message(ADMIN_GROUP_ID,
                           f"💸 <b>Новая заявка на вывод!</b>\n👤 @{cb.from_user.username or cb.from_user.id}\n💰 Сумма: <b>${amount:.2f}</b>")
    await cb.answer()


# --- ПОДДЕРЖКА ---
@dp.message(F.text.contains("Поддержка"))
async def support_btn(msg: Message, state: FSMContext):
    await state.clear()
    supp = normalize_link(await get_setting("support_link"))
    await msg.answer(f"{E_SUPPORT_HTML} <b>Поддержка</b>\n\nВыберите действие:", reply_markup=support_menu_kb(supp))


@dp.callback_query(F.data == "support_new")
async def support_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SupportStates.waiting_msg)
    await cb.message.edit_text("📝 Опишите вашу проблему в одном сообщении.")
    await cb.answer()


@dp.message(SupportStates.waiting_msg)
async def handle_support_msg(msg: Message, state: FSMContext):
    await state.clear()
    t_id = await create_ticket(msg.from_user.id, msg.html_text or "Фото")
    admin_msg = f"🎫 <b>Обращение #{t_id}</b>\n\n👤 {msg.from_user.full_name}\n{E_LINK_HTML} @{msg.from_user.username or '—'}\n🆔 <code>{msg.from_user.id}</code>\n\n💬 <b>Сообщение:</b>\n{msg.html_text}"
    if msg.photo:
        await bot.send_photo(ADMIN_GROUP_ID, msg.photo[-1].file_id, caption=admin_msg,
                             reply_markup=admin_ticket_action_kb(t_id))
    else:
        await bot.send_message(ADMIN_GROUP_ID, admin_msg, reply_markup=admin_ticket_action_kb(t_id))
    await msg.answer(f"{E_SUCCESS_HTML} Обращение #{t_id} создано.", reply_markup=user_ticket_action_kb(t_id))


@dp.callback_query(F.data == "support_my")
async def support_my(cb: CallbackQuery):
    tickets = await get_user_tickets(cb.from_user.id)
    if not tickets: return await cb.answer("У вас пока нет обращений.", show_alert=True)
    for t in tickets:
        status_text = "✅ Закрыто" if t['status'] == 'closed' else "⏳ В ожидании"
        text = f"📁 <b>Обращение #{t['id']}</b> ({status_text})\n\n"
        if t['reply']: text += f"<i>Ответ: {t['reply']}</i>\n"
        kb = user_ticket_action_kb(t['id']) if t['status'] != 'closed' else None
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()


# --- РАБОТА ---
@dp.message(F.text.contains("Начать работу"))
async def start_work(msg: Message, state: FSMContext):
    await state.clear()
    if await is_user_banned(msg.from_user.id): return await msg.answer("⛔ Вы заблокированы.")

    u = await get_user(msg.from_user.id)
    if u['last_reject_time']:
        diff = (datetime.utcnow() - u['last_reject_time']).total_seconds()
        if diff < 900:
            mins = int((900 - diff) // 60)
            return await msg.answer(f"⚠️ Ваша прошлая заявка была отклонена. Кулдаун: {mins} мин.")

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
    possible_ops = [op for op in ops if op["supports_number" if mode == "number" else "supports_qr"]]
    active_ops = [op for op in possible_ops if op["number_active" if mode == "number" else "qr_active"]]
    inactive_ops = [op for op in possible_ops if not op["number_active" if mode == "number" else "qr_active"]]
    text = f"{E_PHONE_HTML} <b>Выберите оператора:</b>"
    if not active_ops:
        text = f"{E_NOT_ACCEPT_HTML} <b>Приём закрыт</b>"
    elif inactive_ops:
        text += f"\n\n{E_NOT_ACCEPT_HTML} <b>Сейчас не принимаются:</b> {', '.join([op['name'] for op in inactive_ops])}"
    await cb.message.edit_text(text, reply_markup=operators_kb(possible_ops, mode, category))
    await cb.answer()


@dp.callback_query(F.data.startswith("op_disabled:"))
async def op_disabled_alert(cb: CallbackQuery):
    op_id = int(cb.data.split(":")[1])
    op = await get_operator(op_id)
    await cb.answer(f"⚠️ У оператора {op['name']} закрыт приём!", show_alert=True)


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


@dp.message(WorkStates.waiting_number, F.text)
async def receive_number(msg: Message, state: FSMContext):
    phone = msg.text.strip()
    if not re.match(r"^\+79\d{9}$", phone):
        return await msg.answer("❗ Формат: <code>+79187382031</code>")

    if await check_duplicate_number("number", phone):
        return await msg.answer(f"{E_FAIL_HTML} Этот номер уже находится на проверке или был оплачен.")

    if ENABLE_REGION_FILTER:
        data = await state.get_data()
        op = await get_operator(data['operator_id'])
        op_name_lower = op['name'].lower()
        if 'мтс' in op_name_lower or 'билайн' in op_name_lower:
            if not any(phone.startswith(p) for p in ALLOWED_PREFIXES):
                return await msg.answer(
                    f"{E_FAIL_HTML} {op['name']} из вашего региона временно не принимается.\nРазрешены: Москва, СПб, Татарстан.")

    data = await state.get_data()
    op = await get_operator(data['operator_id'])
    app_id = await create_application(msg.from_user.id, op['id'], "number", phone_number=phone)
    text = f"🆕 <b>Заявка #{app_id}</b> [{E_PHONE_HTML} Номер]\n\n{E_PROFILE_HTML} {msg.from_user.full_name}\n{E_LINK_HTML} @{msg.from_user.username or '—'}\n\n{E_PHONE_HTML} Оператор: <b>{op['name']}</b>\n☎️ Номер: <code>{phone}</code>\n{E_MONEY_HTML} Цена: ${op['price_number']:.2f}"
    sent = await bot.send_message(ADMIN_GROUP_ID, text, reply_markup=application_admin_kb(app_id, "number"))
    await set_admin_message(app_id, ADMIN_GROUP_ID, sent.message_id)
    await state.clear()
    await msg.answer(f"{E_SUCCESS_HTML} <b>Заявка успешно отправлена!</b>")


@dp.message(WorkStates.waiting_qr_photo, F.photo)
async def qr_photo(msg: Message, state: FSMContext):
    await state.update_data(qr_photo_id=msg.photo[-1].file_id)
    await state.set_state(WorkStates.waiting_qr_number)
    await msg.answer(f"{E_SUCCESS_HTML} Фото получено.\n\n{E_PHONE_HTML} <b>Шаг 2/2:</b> отправь <b>номер от QR</b>:")


@dp.message(WorkStates.waiting_qr_photo)
async def qr_photo_bad(msg: Message):
    await msg.answer("❗ Отправь именно <b>фото</b>.")


@dp.message(WorkStates.waiting_qr_number, F.text)
async def qr_number(msg: Message, state: FSMContext):
    qr_num = msg.text.strip()
    if not re.match(r"^\+79\d{9}$", qr_num):
        return await msg.answer("❗ Формат: <code>+79187382031</code>")

    if await check_duplicate_number("qr", qr_num):
        return await msg.answer(f"{E_FAIL_HTML} Этот QR уже на проверке или оплачен.")

    data = await state.get_data()
    op = await get_operator(data['operator_id'])
    app_id = await create_application(msg.from_user.id, op['id'], "qr", qr_photo_id=data['qr_photo_id'],
                                      qr_number=qr_num)
    caption = f"🆕 <b>Заявка #{app_id}</b> [🖼 QR]\n\n{E_PROFILE_HTML} {msg.from_user.full_name}\n{E_LINK_HTML} @{msg.from_user.username or '—'}\n\n{E_PHONE_HTML} Оператор: <b>{op['name']}</b>\n🔢 Номер QR: <code>{qr_num}</code>\n{E_MONEY_HTML} Цена: ${op['price_qr']:.2f}"
    sent = await bot.send_photo(ADMIN_GROUP_ID, data['qr_photo_id'], caption=caption,
                                reply_markup=application_admin_kb(app_id, "qr"))
    await set_admin_message(app_id, ADMIN_GROUP_ID, sent.message_id)
    await state.clear()
    await msg.answer(f"{E_SUCCESS_HTML} <b>Заявка отправлена!</b>")


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
        await bot.send_message(ADMIN_GROUP_ID, f"⏹ <b>Пользователь отменил запрос кода для #{app['id']}.</b>")
    await cb.message.edit_text(f"{E_FAIL_HTML} Вы отменили запрос кода.")
    await cb.answer()


@dp.message(WorkStates.waiting_code, F.text)
async def catch_code(msg: Message, state: FSMContext):
    app = await get_app_awaiting_code(msg.from_user.id)
    if not app:
        await state.clear()
        return await msg.answer("⚠️ Заявка не найдена.")
    await update_app(app["id"], code=msg.text.strip(), status="code_sent", awaiting_code=0)
    await bot.send_message(ADMIN_GROUP_ID, f"💬 <b>Код для заявки #{app['id']}:</b>\n<code>{msg.text.strip()}</code>")
    await state.clear()
    await msg.answer(f"{E_SUCCESS_HTML} Код отправлен.")


# --- АДМИНКА ---
@dp.message(F.text.contains("Админ-панель"))
async def panel_msg(msg: Message, state: FSMContext):
    await state.clear()
    if not is_admin(msg.from_user.id): return
    await msg.answer("👑 <b>Админ-панель</b>", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "admin_panel")
async def back_to_admin(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text("👑 <b>Админ-панель</b>", reply_markup=admin_panel_kb())
    await cb.answer()


@dp.callback_query(F.data == "close_admin")
async def close_admin(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text("👑 <b>Закрыто.</b>", reply_markup=None)
    await cb.answer()


# --- НАСТРОЙКИ ---
@dp.callback_query(F.data == "adm_settings")
async def adm_settings(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    min_wd = await get_setting("min_withdraw")
    w_start = await get_setting("work_start")
    w_end = await get_setting("work_end")
    supp = await get_setting("support_link")
    text = (f"{E_SETTINGS_HTML} <b>Настройки</b>\n\n"
            f"{E_WALLET_HTML} Мин. вывод: <b>${min_wd}</b>\n"
            f"{E_TIME_HTML} Работа: <b>{w_start} - {w_end}</b>\n"
            f"{E_LINK_HTML} Связь: <b>{supp}</b>")
    await cb.message.edit_text(text, reply_markup=settings_kb())


@dp.callback_query(F.data == "set_min_withdraw")
async def set_mw(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_min_withdraw)
    await cb.message.answer("Введи новую сумму мин. вывода (числом):")
    await cb.answer()


@dp.message(AdminStates.waiting_min_withdraw)
async def save_mw(msg: Message, state: FSMContext):
    try:
        val = float(msg.text.replace(",", "."))
    except:
        return await msg.answer("❗ Число.")
    await set_setting("min_withdraw", val)
    await state.clear()
    await msg.answer(f"{E_SUCCESS_HTML} Сохранено: <b>${val:.2f}</b>")


@dp.callback_query(F.data == "set_work_time")
async def set_wt(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_work_time)
    await cb.message.answer("Введи время работы (пример: <code>08:00-23:00</code>):")
    await cb.answer()


@dp.message(AdminStates.waiting_work_time)
async def save_wt(msg: Message, state: FSMContext):
    try:
        start, end = msg.text.split("-")
        await set_setting("work_start", start.strip())
        await set_setting("work_end", end.strip())
        await state.clear()
        await msg.answer(f"{E_SUCCESS_HTML} График работы: {start} - {end}")
    except:
        await msg.answer("⚠️ Неверный формат. Введи: 08:00-23:00")


@dp.callback_query(F.data == "set_support_link")
async def set_sl(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_support_link)
    await cb.message.answer("Введи ссылку на поддержку (пример: https://t.me/manager или @manager):")
    await cb.answer()


@dp.message(AdminStates.waiting_support_link)
async def save_sl(msg: Message, state: FSMContext):
    await set_setting("support_link", msg.text)
    await state.clear()
    await msg.answer(f"{E_SUCCESS_HTML} Ссылка на связь обновлена.")


# --- ОПЕРАТОРЫ ---
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
        f"⚙️ <b>{op['name']}</b>\n\n📱 Номер: {'🟢 вкл' if op['number_active'] else '🔴 выкл'}\n🖼 QR: {'🟢 вкл' if op['qr_active'] else '🔴 выкл'}",
        reply_markup=operator_edit_kb(op))
    await cb.answer()


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
    await set_all_operators(True)
    await cb.answer("Все операторы включены!", show_alert=True)
    await cb.message.edit_text("👑 <b>Админ-панель</b>\n\n✅ <i>Все операторы включены!</i>",
                               reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "adm_stop_all")
async def adm_stop_all(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await set_all_operators(False)
    await cb.answer("Все операторы выключены!", show_alert=True)
    await cb.message.edit_text("👑 <b>Админ-панель</b>\n\n⏹ <i>Все операторы выключены!</i>",
                               reply_markup=admin_panel_kb())


# --- СТАТИСТИКА ---
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
    async with pool.acquire() as conn:
        users = await conn.fetchval("SELECT COUNT(*) FROM users")
        balance = await conn.fetchval("SELECT COALESCE(SUM(balance),0) FROM users")
        apps = await conn.fetchval("SELECT COUNT(*) FROM applications")
    await cb.message.answer(
        f"{E_TOTAL_HTML} <b>Всего</b>\n\n👥 Юзеров: <b>{users}</b>\n{E_WALLET_HTML} Баланс: <b>${balance:.2f}</b>\n{E_ORDER_HTML} Заявок: <b>{apps}</b>")
    await cb.answer()


# --- РАССЫЛКА ---
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


# --- ВЫПЛАТЫ ---
@dp.callback_query(F.data == "adm_withdrawals")
async def adm_withdrawals(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    ws = await get_pending_withdrawals()
    if not ws: return await cb.answer("Нет активных заявок.")
    await cb.message.edit_text("💸 <b>Заявки на вывод:</b>", reply_markup=withdrawals_kb(ws))


@dp.callback_query(F.data.startswith("adm_pay_w:"))
async def adm_pay_w(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
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
        await bot.send_message(user_id,
                               f"{E_MONEY_HTML} <b>Ваша выплата готова!</b>\nСумма: <b>${amount:.2f}</b>\nСсылка: {link}")
    except:
        pass

    ok, fail, total = await stats_today()
    await cb.message.answer(
        f"{E_SUCCESS_HTML} Выплата #{w_id} на ${amount:.2f} отправлена.\n\n"
        f"{E_STATS_HTML} <b>Стата за сегодня:</b>\n"
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
    if not is_admin(cb.from_user.id): return
    w_id = int(cb.data.split(":")[1])
    await cancel_withdrawal(w_id, "Отменено администратором (сгорело)")
    async with pool.acquire() as conn:
        w = await conn.fetchrow("SELECT user_id, amount FROM withdrawals WHERE id=$1", w_id)
    try:
        await bot.send_message(w['user_id'],
                               f"{E_FAIL_HTML} Заявка на вывод ${w['amount']:.2f} отменена. Средства сгорели.")
    except:
        pass
    await cb.answer("Заявка отменена (деньги списаны).")
    ws = await get_pending_withdrawals()
    if not ws:
        await cb.message.edit_text("💸 Все заявки обработаны.", reply_markup=admin_panel_kb())
    else:
        await cb.message.edit_reply_markup(reply_markup=withdrawals_kb(ws))


# --- ИНФО ЮЗЕРА ---
@dp.callback_query(F.data.startswith("adm_user_info:"))
async def adm_user_info(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app_data = await get_application(app_id)
    u = await get_user(app_data['user_id'])
    is_banned = await is_user_banned(u['user_id'])
    await cb.message.answer(
        f"{E_PROFILE_HTML} <b>Инфо о юзере</b>\n\n"
        f"ID: <code>{u['user_id']}</code>\n"
        f"Юзернейм: @{u['username'] or 'скрыт'}\n"
        f"Баланс: <b>${u['balance']:.2f}</b>\n"
        f"Забанен: {'Да' if is_banned else 'Нет'}",
        reply_markup=user_info_kb(u['user_id'], is_banned)
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_ban:"))
async def ban_user_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    user_id = int(cb.data.split(":")[1])
    await ban_user(user_id)
    await cb.message.edit_text(f"{E_BLOCK_HTML} Юзер {user_id} забанен.", reply_markup=admin_panel_kb())
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_unban:"))
async def unban_user_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    user_id = int(cb.data.split(":")[1])
    await unban_user(user_id)
    await cb.message.edit_text(f"{E_SUCCESS_HTML} Юзер {user_id} разбанен.", reply_markup=admin_panel_kb())
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_add_bal:"))
async def add_bal_cb(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    user_id = int(cb.data.split(":")[1])
    await state.set_state(AdminStates.waiting_balance_amount)
    await state.update_data(user_id=user_id, action="add")
    await cb.message.answer("Введи сумму для начисления:")
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_sub_bal:"))
async def sub_bal_cb(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    user_id = int(cb.data.split(":")[1])
    await state.set_state(AdminStates.waiting_balance_amount)
    await state.update_data(user_id=user_id, action="sub")
    await cb.message.answer("Введи сумму для списания:")
    await cb.answer()


@dp.message(AdminStates.waiting_balance_amount)
async def process_balance_change(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    try:
        amount = float(msg.text)
    except:
        return await msg.answer("Введи число!")
    data = await state.get_data()
    user_id = data['user_id']
    if data['action'] == "add":
        await add_balance(user_id, amount)
        await msg.answer(f"{E_SUCCESS_HTML} Начислено ${amount:.2f} юзеру {user_id}.", reply_markup=admin_panel_kb())
    else:
        await add_balance(user_id, -amount)
        await msg.answer(f"{E_SUCCESS_HTML} Списано ${amount:.2f} юзера {user_id}.", reply_markup=admin_panel_kb())
    await state.clear()


# --- ОБРАБОТКА ЗАЯВОК ---
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
    await safe_edit_app_message(cb.message, f"{E_SUCCESS_HTML} ПРИНЯТА",
                                application_admin_kb(app_id, app["mode"], "accepted"))
    await cb.answer("Принято")


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
    if deduct > 0: await add_balance(app["user_id"], -deduct)
    await update_app(app_id, status="pending", payout_at=None, processed_at=None)
    await increment_orders(app["user_id"], True, -1)
    try:
        await bot.send_message(app["user_id"],
                               f"⚠️ <b>Заявка #{app_id} возвращена на проверку.</b>\nСписано: ${deduct:.2f}")
    except:
        pass
    await safe_edit_app_message(cb.message, f"🔄 ВОЗВРАЩЕНА", application_admin_kb(app_id, app["mode"], "pending"))
    await cb.answer("Возвращено")


@dp.callback_query(F.data.startswith("adm_reject:"))
async def reject(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    app_id = int(cb.data.split(":")[1])
    app = await get_application(app_id)
    if not app or app["status"] in ('accepted', 'rejected', 'cancelled'): return
    if app["mode"] == "number":
        await state.set_state(AdminStates.waiting_reject_reason)
        await state.update_data(reject_app_id=app_id)
        await cb.message.answer(f"✍️ Введи <b>причину</b> для заявки #{app_id}:")
    else:
        await cb.message.edit_reply_markup(reply_markup=reject_reason_kb(app_id))
    await cb.answer()


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
    await update_last_reject(app["user_id"])
    await increment_orders(app["user_id"], False)
    try:
        await bot.send_message(app["user_id"],
                               f"{E_FAIL_HTML} <b>Заявка #{app_id} отклонена.</b>\n\n<b>Причина:</b> {msg.text.strip()}")
    except:
        pass
    await msg.answer(f"{E_FAIL_HTML} Заявка #{app_id} отклонена.")


@dp.callback_query(F.data.startswith("adm_reason:"))
async def adm_reason(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
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
            await bot.send_message(app["user_id"], f"{E_BLOCK_HTML} <b>Номер заблокирован.</b> Списано: ${fine:.2f}")
        except:
            pass
    else:
        try:
            await bot.send_message(app["user_id"], f"{E_FAIL_HTML} Ваш номер слетел.")
        except:
            pass
    await safe_edit_app_message(cb.message, f"{E_FAIL_HTML} ОТКЛОНЕНА ({reason})", None)
    await cb.answer("Отклонено")


# --- ТИКЕТЫ АДМИНА ---
@dp.callback_query(F.data.startswith("adm_reply_ticket:"))
async def adm_reply_ticket(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    t_id = int(cb.data.split(":")[1])
    await state.set_state(AdminSupportStates.waiting_reply)
    await state.update_data(ticket_id=t_id)
    await cb.message.reply("✍️ Введите ответ:")
    await cb.answer()


@dp.message(AdminSupportStates.waiting_reply)
async def admin_send_reply(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    t_id = data.get("ticket_id")
    await state.clear()
    await reply_ticket(t_id, msg.html_text)
    async with pool.acquire() as conn:
        t = await conn.fetchrow("SELECT user_id FROM tickets WHERE id=$1", t_id)
    if t:
        try:
            await bot.send_message(t['user_id'], f"🎧 <b>Ответ по обращению #{t_id}:</b>\n\n{msg.html_text}",
                                   reply_markup=user_ticket_action_kb(t_id))
        except:
            pass
    await msg.answer(f"{E_SUCCESS_HTML} Ответ отправлен!")


@dp.callback_query(F.data.startswith("adm_close_ticket:"))
async def adm_close_ticket(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    t_id = int(cb.data.split(":")[1])
    await close_ticket(t_id)
    await cb.message.edit_text(f"{E_SUCCESS_HTML} Закрыто.", reply_markup=None)
    await cb.answer()


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
                    await bot.send_message(app["user_id"], f"{E_SUCCESS_HTML} Материал засчитан! +${price:.2f}")
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
            now = datetime.utcnow() + timedelta(hours=3)
            current_time = now.strftime("%H:%M")
            is_working = start_str <= current_time <= end_str
            ops = await get_operators()
            any_active = any(op["number_active"] or op["qr_active"] for op in ops)
            if is_working and not any_active:
                await set_all_operators(True)
            elif not is_working and any_active:
                await set_all_operators(False)
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