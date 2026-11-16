import asyncio, logging, csv, io
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart
import aiosqlite

from config import (BOT_TOKEN, ADMIN_IDS, ADMIN_GROUP_ID, REF_BONUS, QR_COOLDOWN_MINUTES,
                    PHONE_REGEX, SUPPORT_LINK, CHANNEL_ID, ALLOWED_PREFIXES,
                    ENABLE_REGION_FILTER, _normalize_tg_link)
from database import *
from keyboards import *
from middlewares.subscription import SubscriptionMiddleware
from cryptobot import get_crypto_balance, create_check

# Premium emoji
E_GREET = '<tg-emoji emoji-id="5258501105293205250">👋</tg-emoji>'
E_PROF = '<tg-emoji emoji-id="5258011929993026890">👤</tg-emoji>'
E_SUP = '<tg-emoji emoji-id="5316727448644103237">🎧</tg-emoji>'
E_WAL = '<tg-emoji emoji-id="5258204546391351475">💳</tg-emoji>'
E_ST = '<tg-emoji emoji-id="5258330865674494479">📊</tg-emoji>'
E_OK = '<tg-emoji emoji-id="5260416304224936047">✅</tg-emoji>'
E_NO = '<tg-emoji emoji-id="5260342697075416641">❌</tg-emoji>'
E_TOT = '<tg-emoji emoji-id="5258057130228849960">🌐</tg-emoji>'
E_CAL = '<tg-emoji emoji-id="5258105663359294787">📅</tg-emoji>'
E_M = '<tg-emoji emoji-id="5258368777350816286">💰</tg-emoji>'
E_BL = '<tg-emoji emoji-id="5258318620722733379">🚫</tg-emoji>'
E_ACC = '<tg-emoji emoji-id="5258501105293205250">👏</tg-emoji>'
E_PH = '<tg-emoji emoji-id="5258337316715373336">📱</tg-emoji>'
E_ORD = '<tg-emoji emoji-id="5258461531464539536">📌</tg-emoji>'
E_BC = '<tg-emoji emoji-id="5258089153505009279">📣</tg-emoji>'
E_DN = '<tg-emoji emoji-id="5231102735817918643">👇</tg-emoji>'
E_LNK = '<tg-emoji emoji-id="5260730055880876557">🔗</tg-emoji>'
E_NAC = '<tg-emoji emoji-id="5260249440450520061">🖐</tg-emoji>'
E_INF = '<tg-emoji emoji-id="5879770735999717115">👤</tg-emoji>'
E_SET = '<tg-emoji emoji-id="6021582331251268218">⚙️</tg-emoji>'
E_CLK = '<tg-emoji emoji-id="6034898821517940846">⏰</tg-emoji>'


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
    waiting_unban_id = State()
    waiting_min_withdraw = State()
    waiting_work_start = State()
    waiting_work_end = State()
    waiting_urgent_link = State()
    waiting_user_balance_amount = State()
    waiting_user_id_lookup = State()


class SupportStates(StatesGroup):
    waiting_msg = State()
    waiting_reply = State()


class AdminSupportStates(StatesGroup):
    waiting_reply = State()


bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def is_admin(uid): return uid in ADMIN_IDS


async def check_maintenance(uid):
    if is_admin(uid): return False
    return await is_maintenance()


def is_allowed_region(phone):
    if not ENABLE_REGION_FILTER: return True
    return any(phone.startswith(p) for p in ALLOWED_PREFIXES)


async def safe_edit_app_message(message, new_status_text, reply_markup):
    try:
        if message.photo:
            base = (message.caption or "").split('Статус:')[0].strip()
            await message.edit_caption(caption=f"{base}\n\nСтатус: {new_status_text}", reply_markup=reply_markup)
        else:
            base = (message.text or "").split('Статус:')[0].strip()
            await message.edit_text(text=f"{base}\n\nСтатус: {new_status_text}", reply_markup=reply_markup)
    except Exception:
        try: await message.reply(f"Статус: {new_status_text}", reply_markup=reply_markup)
        except Exception: pass


async def get_mode_message_and_kb(mode):
    ops = await get_operators()
    if mode == "number":
        possible = [op for op in ops if op["supports_number"]]; field = "number_active"
    else:
        possible = [op for op in ops if op["supports_qr"]]; field = "qr_active"
    active = [op for op in possible if op[field]]
    inactive = [op for op in possible if not op[field]]
    if not active:
        text = (f"{E_NAC} <b>Приём операторов сейчас закрыт</b>\n\nЗаглядывайте позже." if mode == "number"
                else f"{E_NAC} <b>Готовые QR сейчас не принимаются</b>\n\nЗаглядывайте позже.")
    else:
        text = f"{E_PH} <b>Выберите оператора:</b>"
        if inactive:
            text += f"\n\n{E_NAC} <b>Сейчас не принимаются:</b> " + ", ".join(op['name'] for op in inactive)
    return text, operators_kb(possible, mode, 'regular')


# ========== START / SUB ==========
@dp.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    if await is_user_banned(msg.from_user.id):
        return await msg.answer(f"{E_BL} Вы заблокированы. Обратитесь в поддержку.")
    ref_id = None
    parts = msg.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            r = int(parts[1][4:])
            if r != msg.from_user.id: ref_id = r
        except ValueError: pass
    await create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name, ref_id)
    try:
        m = await msg.bot.get_chat_member(CHANNEL_ID, msg.from_user.id)
        ok = m.status not in ("left", "kicked")
    except Exception: ok = False
    if ok:
        await msg.answer(f"{E_GREET} Привет, <b>{msg.from_user.full_name}</b>!\n\nМеню ниже {E_DN}",
                         reply_markup=main_menu_kb(is_admin(msg.from_user.id)))
    else:
        await msg.answer(f"{E_GREET} Привет, <b>{msg.from_user.full_name}</b>!\n\nПодпишись на канал.", reply_markup=sub_kb())


@dp.callback_query(F.data == "check_sub")
async def check_sub(cb: CallbackQuery):
    if await is_user_banned(cb.from_user.id):
        return await cb.answer("Вы заблокированы.", show_alert=True)
    try:
        m = await cb.bot.get_chat_member(CHANNEL_ID, cb.from_user.id)
        ok = m.status not in ("left", "kicked")
    except Exception: ok = False
    if not ok: return await cb.answer("Подписка не найдена.", show_alert=True)
    await cb.message.edit_text(f"{E_OK} Подписка подтверждена!")
    await cb.message.answer("Добро пожаловать!", reply_markup=main_menu_kb(is_admin(cb.from_user.id)))
    await cb.answer()


# ========== PROFILE ==========
RANKS = [(0, "Новичок"), (5, "Любитель"), (15, "Про"), (50, "Мастер"), (100, "Легенда")]


def get_rank_info(s):
    cn, cm = RANKS[0]; nn, nm = None, None
    for i, (th, n) in enumerate(RANKS):
        if s >= th:
            cn, cm = n, th
            if i + 1 < len(RANKS): nm, nn = RANKS[i + 1]
    pct = 100 if nm is None else (s - cm) / (nm - cm) * 100
    return cn, pct, nn, nm


@dp.message(F.text.contains("Мой профиль"))
async def profile(msg: Message):
    if await is_user_banned(msg.from_user.id):
        return await msg.answer(f"{E_BL} Вы заблокированы.")
    u = await get_user(msg.from_user.id)
    if not u: return await msg.answer("Нажми /start.")
    pa = await pending_amount(msg.from_user.id)
    av = u['balance']
    pw = await get_pending_withdrawn(msg.from_user.id)
    wd = await get_total_withdrawn(msg.from_user.id)
    fn = await get_total_fines(msg.from_user.id)
    te = av + pa + pw + wd + fn
    try:
        cdt = datetime.strptime(u['created_at'].split('.')[0], "%Y-%m-%d %H:%M:%S")
        days = (datetime.utcnow() - cdt).days + 1; cs = cdt.strftime("%d.%m.%Y")
    except Exception: days, cs = 1, "—"
    rn, rp, nn, nt = get_rank_info(u['successful_orders'])
    rpos = await get_user_rank(msg.from_user.id)
    rc, ra = await get_referral_stats(msg.from_user.id)
    wa, wr, ws = await get_user_weekly_stats(msg.from_user.id)
    try:
        me = await bot.get_me()
        rl = f"https://t.me/{me.username}?start=ref_{msg.from_user.id}"
    except Exception: rl = "—"
    rline = f"{rn} ({rp:.0f}% → {nn}, осталось {nt - u['successful_orders']})" if nn else f"{rn} (максимум)"
    t = (f"{E_PROF} <b>Мой профиль</b>\n\n"
         f"{E_WAL} <b>Заработано:</b> <b>${te:.2f}</b>\n"
         f"├ Доступно: <b>${av:.2f}</b>\n├ На проверке: <b>${pa:.2f}</b>\n"
         f"├ На выводе: <b>${pw:.2f}</b>\n├ Выведено: <b>${wd:.2f}</b>\n└ Штрафы: <b>${fn:.2f}</b>\n\n"
         f"{E_ST} <b>Статистика:</b>\n├ Успешно: <b>{u['successful_orders']}</b>\n"
         f"├ Неуспешно: <b>{u['failed_orders']}</b>\n└ Всего: <b>{u['successful_orders']+u['failed_orders']}</b>\n\n"
         f"<b>Ранг #{rpos}:</b> {rline}\n\n"
         f"{E_CAL} <b>За 7 дней:</b>\n├ Принято: <b>{wa}</b>\n├ Отклонено: <b>{wr}</b>\n└ Заработано: <b>${ws:.2f}</b>\n\n"
         f"{E_LNK} <b>Рефералы:</b>\n├ Приглашено: <b>{rc}</b> (активных: {ra})\n└ Ссылка: <code>{rl}</code>\n\n"
         f"{E_CAL} С нами с {cs} ({days} дн.)")
    await msg.answer(t, reply_markup=profile_kb(), disable_web_page_preview=True)


@dp.callback_query(F.data == "leaderboard")
async def leaderboard(cb: CallbackQuery):
    top = await get_top_users(10)
    if not top: return await cb.answer("Пока нет данных.", show_alert=True)
    t = f"{E_ST} <b>Топ-10</b>\n\n"
    for i, u in enumerate(top, 1):
        n = f"@{u['username']}" if u['username'] else (u['full_name'] or f"ID {u['user_id']}")
        t += f"{i}. {n} — <b>{u['successful_orders']}</b> заявок\n"
    try: await cb.message.edit_text(t, reply_markup=leaderboard_kb())
    except Exception: await cb.message.answer(t, reply_markup=leaderboard_kb())
    await cb.answer()


@dp.callback_query(F.data == "audit_log")
async def audit_log(cb: CallbackQuery):
    apps = await get_user_applications(cb.from_user.id)
    if not apps: return await cb.answer("Заявок нет.", show_alert=True)
    t = f"{E_ORD} <b>Журнал заявок:</b>\n\n"
    for a in apps:
        st = STATUS_RU.get(a['status'], a['status'])
        v = a['phone_number'] if a['mode'] == 'number' else a['qr_number']
        t += f"<b>#{a['id']}</b> | {a['mode'].upper()} | {v}\nСтатус: {st}\n\n"
    await cb.message.answer(t)
    await cb.answer()


@dp.callback_query(F.data == "withdraw_history")
async def withdraw_history(cb: CallbackQuery):
    wds = await get_user_withdrawals(cb.from_user.id)
    if not wds: return await cb.answer("Выплат нет.", show_alert=True)
    t = f"{E_M} <b>История выплат:</b>\n\n"
    sm = {"completed": "Выплачено", "pending": "В обработке", "cancelled": "Отменено"}
    items = []
    for w in wds:
        st = sm.get(w['status'], w['status'])
        d = (w['created_at'] or "").split('.')[0]
        t += f"<b>#{w['id']}</b> | ${w['amount']:.2f}\nДата: {d}\nСтатус: {st}\n"
        if w['status'] == 'cancelled':
            t += f"<i>Причина: {w['reject_reason'] or '—'}</i>\n"
        t += "\n"; items.append(w)
    await cb.message.answer(t, reply_markup=withdraw_history_checks_kb(items), disable_web_page_preview=True)
    await cb.answer()


# ========== SUPPORT ==========
@dp.message(F.text.contains("Поддержка"))
async def support_btn(msg: Message, state: FSMContext):
    await state.clear()
    if await is_user_banned(msg.from_user.id):
        return await msg.answer(f"{E_BL} Вы заблокированы.")
    urgent = await get_urgent_support_link() or SUPPORT_LINK
    await msg.answer(f"{E_SUP} <b>Поддержка</b>\n\nВыберите действие:", reply_markup=support_menu_kb(urgent))


@dp.callback_query(F.data == "support_new")
async def support_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SupportStates.waiting_msg)
    await cb.message.edit_text("Опишите проблему одним сообщением.")
    await cb.answer()


@dp.message(SupportStates.waiting_msg)
async def handle_support_msg(msg: Message, state: FSMContext):
    await state.clear()
    tid = await create_ticket(msg.from_user.id, msg.html_text or "Фото/Медиа")
    am = (f"<b>Обращение #{tid}</b>\n\n<b>От:</b> {msg.from_user.full_name}\n"
          f"{E_LNK} @{msg.from_user.username or '—'}\n<code>{msg.from_user.id}</code>\n\n"
          f"<b>Сообщение:</b>\n{msg.html_text}")
    if msg.photo:
        await bot.send_photo(ADMIN_GROUP_ID, msg.photo[-1].file_id, caption=am, reply_markup=admin_ticket_action_kb(tid))
    else:
        await bot.send_message(ADMIN_GROUP_ID, am, reply_markup=admin_ticket_action_kb(tid))
    await msg.answer(f"{E_OK} Обращение #{tid} создано.", reply_markup=user_ticket_action_kb(tid))


@dp.callback_query(F.data == "support_my")
async def support_my(cb: CallbackQuery):
    tickets = await get_user_tickets(cb.from_user.id)
    if not tickets: return await cb.answer("Обращений нет.", show_alert=True)
    for t in tickets:
        st = "Закрыто" if t['status'] == 'closed' else "В ожидании"
        txt = f"<b>Обращение #{t['id']}</b> ({st})\n\n"
        if t['reply']: txt += f"<i>Ответ: {t['reply']}</i>\n"
        kb = user_ticket_action_kb(t['id']) if t['status'] != 'closed' else None
        await cb.message.answer(txt, reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data.startswith("user_reply_ticket:"))
async def user_reply_ticket(cb: CallbackQuery, state: FSMContext):
    tid = int(cb.data.split(":")[1])
    await state.set_state(SupportStates.waiting_reply)
    await state.update_data(ticket_id=tid)
    await cb.message.reply("Напишите ваш ответ:")
    await cb.answer()


@dp.message(SupportStates.waiting_reply)
async def user_send_reply(msg: Message, state: FSMContext):
    data = await state.get_data(); tid = data.get("ticket_id"); await state.clear()
    am = (f"<b>Обращение #{tid} (Ответ юзера)</b>\n\n<b>От:</b> {msg.from_user.full_name}\n"
          f"<code>{msg.from_user.id}</code>\n\n<b>Сообщение:</b>\n{msg.html_text}")
    if msg.photo:
        await bot.send_photo(ADMIN_GROUP_ID, msg.photo[-1].file_id, caption=am, reply_markup=admin_ticket_action_kb(tid))
    else:
        await bot.send_message(ADMIN_GROUP_ID, am, reply_markup=admin_ticket_action_kb(tid))
    await msg.answer(f"{E_OK} Ответ отправлен.", reply_markup=user_ticket_action_kb(tid))


@dp.callback_query(F.data.startswith("user_close_ticket:"))
async def user_close_ticket(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    await reply_ticket(tid, "Пользователь отметил проблему решенной"); await close_ticket(tid)
    await cb.message.edit_text(f"{E_OK} Обращение #{tid} закрыто. Спасибо!", reply_markup=None)
    try: await bot.send_message(ADMIN_GROUP_ID, f"<b>Обращение #{tid}</b> закрыто пользователем.")
    except Exception: pass
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_reply_ticket:"))
async def adm_reply_ticket(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    tid = int(cb.data.split(":")[1])
    await state.set_state(AdminSupportStates.waiting_reply)
    await state.update_data(ticket_id=tid)
    await cb.message.reply("Введите ответ для пользователя:")
    await cb.answer()


@dp.message(AdminSupportStates.waiting_reply)
async def admin_send_reply(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data(); tid = data.get("ticket_id"); await state.clear()
    await reply_ticket(tid, msg.html_text)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM tickets WHERE id=?", (tid,)) as c:
            t = await c.fetchone()
    if t:
        try: await bot.send_message(t['user_id'], f"<b>Ответ по обращению #{tid}:</b>\n\n{msg.html_text}",
                                    reply_markup=user_ticket_action_kb(tid))
        except Exception: pass
    await msg.answer(f"{E_OK} Ответ отправлен.")


@dp.callback_query(F.data.startswith("adm_close_ticket:"))
async def adm_close_ticket(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    tid = int(cb.data.split(":")[1])
    await reply_ticket(tid, "Закрыто администратором"); await close_ticket(tid)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM tickets WHERE id=?", (tid,)) as c:
            t = await c.fetchone()
    if t:
        try: await bot.send_message(t['user_id'], f"<b>Обращение #{tid} закрыто администратором.</b>")
        except Exception: pass
    await cb.message.edit_text(f"Обращение #{tid} закрыто.", reply_markup=None)
    await cb.answer()


# ========== WITHDRAW ==========
@dp.callback_query(F.data == "withdraw")
async def withdraw(cb: CallbackQuery):
    if await check_maintenance(cb.from_user.id):
        return await cb.answer("Тех.работы. Попробуйте позже.", show_alert=True)
    u = await get_user(cb.from_user.id); amount = u["balance"]; mw = await get_min_withdraw()
    if amount < mw:
        return await cb.answer(f"Минимум: ${mw:.2f}\nБаланс: ${amount:.2f}", show_alert=True)
    await create_withdrawal(cb.from_user.id, amount)
    await cb.message.answer(f"{E_OK} Заявка на вывод <b>${amount:.2f}</b> создана!")
    try: await bot.send_message(ADMIN_GROUP_ID,
        f"<b>Новая заявка на вывод</b>\n\n{cb.from_user.full_name}\n"
        f"<code>{cb.from_user.id}</code>\nСумма: <b>${amount:.2f}</b>")
    except Exception: pass
    await cb.answer()


# ========== WORK ==========
@dp.message(F.text.contains("Начать работу"))
async def start_work(msg: Message, state: FSMContext):
    await state.clear()
    if await is_user_banned(msg.from_user.id): return await msg.answer(f"{E_BL} Вы заблокированы.")
    if await check_maintenance(msg.from_user.id):
        return await msg.answer("<b>Тех.работы</b>\n\nПриём временно приостановлен.",
                                reply_markup=main_menu_kb(is_admin(msg.from_user.id)))
    await state.set_state(WorkStates.choosing_operator)
    await state.update_data(mode="number")
    text, kb = await get_mode_message_and_kb("number")
    await msg.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("mode:"))
async def choose_mode(cb: CallbackQuery, state: FSMContext):
    if await check_maintenance(cb.from_user.id): return await cb.answer("Тех.работы.", show_alert=True)
    mode = cb.data.split(":")[1]
    await state.update_data(mode=mode)
    text, kb = await get_mode_message_and_kb(mode)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data == "back_main")
async def back_main_inline(cb: CallbackQuery):
    await cb.message.edit_text("Главное меню внизу.", reply_markup=None); await cb.answer()


@dp.callback_query(F.data == "ignore")
async def ignore_cb(cb: CallbackQuery): await cb.answer()


@dp.callback_query(F.data.startswith("cat:"))
async def switch_category(cb: CallbackQuery):
    _, mode, cat = cb.data.split(":")
    ops = await get_operators()
    if mode == "number":
        possible = [op for op in ops if op["supports_number"]]; field = "number_active"
    else:
        possible = [op for op in ops if op["supports_qr"]]; field = "qr_active"
    active = [op for op in possible if op[field]]; inactive = [op for op in possible if not op[field]]
    text = f"{E_PH} <b>Выберите оператора:</b>"
    if not active: text = f"{E_NAC} <b>Приём закрыт</b>"
    elif inactive: text += f"\n\n{E_NAC} <b>Не принимаются:</b> " + ", ".join(op['name'] for op in inactive)
    await cb.message.edit_text(text, reply_markup=operators_kb(possible, mode, cat))
    await cb.answer()


@dp.callback_query(F.data.startswith("op_disabled:"))
async def op_disabled_alert(cb: CallbackQuery):
    oid = int(cb.data.split(":")[1]); op = await get_operator(oid)
    await cb.message.answer(f"<b>{op['name']}</b> — приём закрыт.\n\nУведомить о включении?",
                            reply_markup=adm_notify_operator_kb(oid))
    await cb.answer()


@dp.callback_query(F.data.startswith("notify_op:"))
async def notify_op_sub(cb: CallbackQuery):
    oid = int(cb.data.split(":")[1]); await sub_to_operator(cb.from_user.id, oid)
    await cb.message.edit_text("Вы подписались! Мы напишем, когда оператор включится.")
    await cb.answer("Вы подписаны!")


@dp.callback_query(F.data.startswith("op:"))
async def choose_operator(cb: CallbackQuery, state: FSMContext):
    if await check_maintenance(cb.from_user.id): return await cb.answer("Тех.работы.", show_alert=True)
    _, mode, oid = cb.data.split(":"); op = await get_operator(int(oid))
    await state.update_data(operator_id=op["id"], mode=mode)
    if mode == "number":
        await state.set_state(WorkStates.waiting_number)
        await cb.message.edit_text(f"{E_PH} <b>{op['name']}</b>\n{E_M} ${op['price_number']:.2f}\n\nОтправь <b>номер</b>:")
    else:
        await state.set_state(WorkStates.waiting_qr_photo)
        await cb.message.edit_text(f"<b>{op['name']}</b>\n{E_M} ${op['price_qr']:.2f}\n\n<b>Шаг 1/2:</b> фото QR:")
    await cb.answer()


# ========== NUMBER / QR ==========
@dp.message(WorkStates.waiting_number, F.text)
async def receive_number(msg: Message, state: FSMContext):
    if await check_maintenance(msg.from_user.id):
        await state.clear(); return await msg.answer("Тех.работы.")
    phone = msg.text.strip()
    if not PHONE_REGEX.match(phone): return await msg.answer("Формат: <code>+79187382031</code>")
    if not is_allowed_region(phone): return await msg.answer(f"{E_NO} Регион не поддерживается.")
    cd = await get_setting_int("rejection_cooldown", 15)
    lr = await get_last_rejection_time(msg.from_user.id)
    if lr:
        try:
            dt = datetime.strptime(lr.split('.')[0], "%Y-%m-%d %H:%M:%S")
            diff = (datetime.utcnow() - dt).total_seconds()
            if diff < cd * 60:
                return await msg.answer(f"{E_CLK} После отклонения нельзя сдавать ещё <b>{int((cd*60-diff)//60)+1} мин</b>.")
        except Exception: pass
    if await check_number_already_accepted("number", phone):
        return await msg.answer(f"{E_NO} Номер уже сдан или висит на проверке.")
    data = await state.get_data(); op = await get_operator(data["operator_id"])
    aid = await create_application(user_id=msg.from_user.id, operator_id=op["id"], mode="number", phone_number=phone)
    t = (f"<b>Заявка #{aid}</b> [Номер]\n\n{E_PROF} {msg.from_user.full_name}\n{E_LNK} @{msg.from_user.username or '—'}\n"
         f"<code>{msg.from_user.id}</code>\n\n{E_PH} <b>{op['name']}</b>\nНомер: <code>{phone}</code>\n{E_M} ${op['price_number']:.2f}")
    sent = await bot.send_message(ADMIN_GROUP_ID, t, reply_markup=application_admin_kb(aid, "number", "pending", msg.from_user.id))
    await set_admin_message(aid, ADMIN_GROUP_ID, sent.message_id)
    await state.clear()
    await msg.answer(f"{E_OK} <b>Заявка отправлена на проверку!</b>")


@dp.message(WorkStates.waiting_qr_photo, F.photo)
async def qr_photo(msg: Message, state: FSMContext):
    await state.update_data(qr_photo_id=msg.photo[-1].file_id)
    await state.set_state(WorkStates.waiting_qr_number)
    await msg.answer(f"{E_OK} Фото получено.\n\n<b>Шаг 2/2:</b> отправь <b>номер от QR</b>:")


@dp.message(WorkStates.waiting_qr_photo)
async def qr_photo_bad(msg: Message): await msg.answer("Отправь именно <b>фото</b>.")


@dp.message(WorkStates.waiting_qr_number, F.text)
async def qr_number(msg: Message, state: FSMContext):
    if await check_maintenance(msg.from_user.id):
        await state.clear(); return await msg.answer("Тех.работы.")
    qn = msg.text.strip()
    if not PHONE_REGEX.match(qn): return await msg.answer("Формат: <code>+79187382031</code>")
    if not is_allowed_region(qn): return await msg.answer(f"{E_NO} Регион не поддерживается.")
    cd = await get_setting_int("rejection_cooldown", 15)
    lr = await get_last_rejection_time(msg.from_user.id)
    if lr:
        try:
            dt = datetime.strptime(lr.split('.')[0], "%Y-%m-%d %H:%M:%S")
            diff = (datetime.utcnow() - dt).total_seconds()
            if diff < cd * 60:
                return await msg.answer(f"{E_CLK} После отклонения нельзя сдавать ещё <b>{int((cd*60-diff)//60)+1} мин</b>.")
        except Exception: pass
    if await check_number_already_accepted("qr", qn):
        return await msg.answer(f"{E_NO} QR уже сдан или висит на проверке.")
    data = await state.get_data(); op = await get_operator(data["operator_id"])
    aid = await create_application(user_id=msg.from_user.id, operator_id=op["id"], mode="qr",
                                   qr_photo_id=data["qr_photo_id"], qr_number=qn)
    cap = (f"<b>Заявка #{aid}</b> [QR]\n\n{E_PROF} {msg.from_user.full_name}\n{E_LNK} @{msg.from_user.username or '—'}\n"
           f"<code>{msg.from_user.id}</code>\n\n{E_PH} <b>{op['name']}</b>\nНомер QR: <code>{qn}</code>\n{E_M} ${op['price_qr']:.2f}")
    sent = await bot.send_photo(ADMIN_GROUP_ID, photo=data["qr_photo_id"], caption=cap,
                                reply_markup=application_admin_kb(aid, "qr", "pending", msg.from_user.id))
    await set_admin_message(aid, ADMIN_GROUP_ID, sent.message_id)
    await state.clear()
    await msg.answer(f"{E_OK} <b>Заявка отправлена на проверку!</b>")


# ========== CODE ==========
@dp.callback_query(F.data == "user_write_code")
async def user_write_code(cb: CallbackQuery, state: FSMContext):
    await state.set_state(WorkStates.waiting_code)
    await cb.message.edit_text("Отправь код одним сообщением:")
    await cb.answer()


@dp.callback_query(F.data == "user_cancel_code")
async def user_cancel_code(cb: CallbackQuery):
    app = await get_app_awaiting_code(cb.from_user.id)
    if app:
        await update_app(app["id"], status="cancelled", awaiting_code=0)
        try: await bot.send_message(ADMIN_GROUP_ID, f"<b>Юзер отменил запрос кода для #{app['id']}.</b>")
        except Exception: pass
    await cb.message.edit_text("Вы отменили запрос кода.")
    await cb.answer()


@dp.message(WorkStates.waiting_code, F.text)
async def catch_code(msg: Message, state: FSMContext):
    app = await get_app_awaiting_code(msg.from_user.id)
    if not app:
        await state.clear(); return await msg.answer("Активная заявка не найдена.")
    await update_app(app["id"], code=msg.text.strip(), status="code_sent", awaiting_code=0)
    try: await bot.send_message(ADMIN_GROUP_ID, f"<b>Код для заявки #{app['id']}:</b>\n<code>{msg.text.strip()}</code>")
    except Exception: pass
    await state.clear()
    await msg.answer(f"{E_OK} Код отправлен.")


# ========== ADMIN PANEL ==========
@dp.message(F.text.contains("Админ-панель"))
async def panel_msg(msg: Message, state: FSMContext):
    await state.clear()
    if not is_admin(msg.from_user.id): return await msg.answer(f"Нет доступа.\nID: <code>{msg.from_user.id}</code>")
    aw = await get_setting("auto_work"); st = "Включен" if aw == "1" else "Отключен"
    ws, we = await get_work_start(), await get_work_end()
    mt = " | ТЕХ.РАБОТЫ" if await is_maintenance() else ""
    await msg.answer(f"<b>Админ-панель</b>\n\n<i>Авто ({ws}–{we}): {st}{mt}</i>", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "admin_panel")
async def back_to_admin(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    aw = await get_setting("auto_work"); st = "Включен" if aw == "1" else "Отключен"
    ws, we = await get_work_start(), await get_work_end()
    mt = " | ТЕХ.РАБОТЫ" if await is_maintenance() else ""
    await cb.message.edit_text(f"<b>Админ-панель</b>\n\n<i>Авто ({ws}–{we}): {st}{mt}</i>", reply_markup=admin_panel_kb())
    await cb.answer()


@dp.callback_query(F.data == "close_admin")
async def close_admin(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text("Админ-панель закрыта.", reply_markup=None); await cb.answer()


# ========== MAINTENANCE ==========
@dp.callback_query(F.data == "adm_maintenance")
async def adm_maintenance(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    on = await is_maintenance(); st = "ВКЛ" if on else "ВЫКЛ"
    await cb.message.edit_text(
        f"<b>Тех.работы</b>\n\nСтатус: <b>{st}</b>\n\n"
        f"Когда включено — юзеры не могут сдавать/выводить. Админы работают.",
        reply_markup=adm_maintenance_kb(on))
    await cb.answer()


@dp.callback_query(F.data == "adm_toggle_maintenance")
async def adm_toggle_maintenance(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    cur = await is_maintenance(); await set_setting("maintenance", "0" if cur else "1")
    await add_admin_log(cb.from_user.id, "Тех.работы", "ВЫКЛ" if cur else "ВКЛ")
    on = not cur; st = "ВКЛ" if on else "ВЫКЛ"
    await cb.message.edit_text(f"<b>Тех.работы</b>\n\nСтатус: <b>{st}</b>", reply_markup=adm_maintenance_kb(on))
    await cb.answer(f"Тех.работы: {st}", show_alert=True)


# ========== SETTINGS ==========
@dp.callback_query(F.data == "adm_settings")
async def adm_settings(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    mw = await get_min_withdraw(); ws, we = await get_work_start(), await get_work_end()
    u = await get_urgent_support_link() or "—"; ap = "ВКЛ" if await is_auto_payout() else "ВЫКЛ"
    t = (f"{E_SET} <b>Настройки</b>\n\n{E_M} Мин. вывод: <b>${mw:.2f}</b>\n"
         f"{E_CLK} Время: <b>{ws} – {we}</b>\n{E_LNK} Срочная связь: {u}\n{E_WAL} Авто-выплаты: <b>{ap}</b>")
    await cb.message.edit_text(t, reply_markup=adm_settings_kb(), disable_web_page_preview=True)
    await cb.answer()


@dp.callback_query(F.data == "adm_set_autopayout")
async def adm_set_autopayout(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    cur = await is_auto_payout(); await set_setting("auto_payout", "0" if cur else "1")
    await add_admin_log(cb.from_user.id, "Авто-выплаты", "ВЫКЛ" if cur else "ВКЛ")
    await cb.answer(f"Авто-выплаты: {'ВЫКЛ' if cur else 'ВКЛ'}", show_alert=True)
    await adm_settings(cb)


@dp.callback_query(F.data == "adm_set_min")
async def adm_set_min(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.set_state(AdminStates.waiting_min_withdraw)
    await cb.message.answer("Мин. сумма вывода в $:"); await cb.answer()


@dp.message(AdminStates.waiting_min_withdraw)
async def save_min_withdraw(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    try:
        v = float(msg.text.replace(",", "."))
        if v < 0: raise ValueError
    except Exception: return await msg.answer("Некорректно.")
    await set_setting("min_withdraw", f"{v:.2f}"); await state.clear()
    await add_admin_log(msg.from_user.id, "Мин. вывод", f"${v:.2f}")
    await msg.answer(f"{E_OK} Мин. вывод = <b>${v:.2f}</b>", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "adm_set_hours")
async def adm_set_hours(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    ws, we = await get_work_start(), await get_work_end()
    await cb.message.edit_text(f"Текущее: <b>{ws} – {we}</b>", reply_markup=adm_hours_kb()); await cb.answer()


@dp.callback_query(F.data == "adm_set_start")
async def adm_set_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.set_state(AdminStates.waiting_work_start)
    await cb.message.answer("Начало ворка (HH:MM):"); await cb.answer()


@dp.message(AdminStates.waiting_work_start)
async def save_work_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    v = msg.text.strip()
    try: datetime.strptime(v, "%H:%M")
    except ValueError: return await msg.answer("Формат: <code>06:00</code>")
    await set_setting("work_start", v); await state.clear()
    await add_admin_log(msg.from_user.id, "Начало ворка", v)
    await msg.answer(f"{E_OK} Начало: <b>{v}</b>", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "adm_set_end")
async def adm_set_end(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.set_state(AdminStates.waiting_work_end)
    await cb.message.answer("Конец ворка (HH:MM):"); await cb.answer()


@dp.message(AdminStates.waiting_work_end)
async def save_work_end(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    v = msg.text.strip()
    try: datetime.strptime(v, "%H:%M")
    except ValueError: return await msg.answer("Формат: <code>19:00</code>")
    await set_setting("work_end", v); await state.clear()
    await add_admin_log(msg.from_user.id, "Конец ворка", v)
    await msg.answer(f"{E_OK} Конец: <b>{v}</b>", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "adm_set_urgent")
async def adm_set_urgent(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.set_state(AdminStates.waiting_urgent_link)
    await cb.message.answer("Ссылка для Срочной связи:"); await cb.answer()


@dp.message(AdminStates.waiting_urgent_link)
async def save_urgent_link(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    link = _normalize_tg_link(msg.text.strip())
    if not link: return await msg.answer("Некорректно.")
    await set_setting("urgent_support_link", link); await state.clear()
    await add_admin_log(msg.from_user.id, "Срочная связь", link)
    await msg.answer(f"{E_OK} Срочная связь: {link}", reply_markup=admin_panel_kb(), disable_web_page_preview=True)


# ========== ANALYTICS / ACTIVE / CSV ==========
@dp.callback_query(F.data == "adm_analytics")
async def adm_analytics(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    d = await get_advanced_stats()
    conv = (d["accepted"] / d["total"] * 100) if d["total"] else 0
    t = f"{E_ST} <b>Аналитика</b>\n\n<b>Топ-5 юзеров:</b>\n"
    if d["top_users"]:
        for i, u in enumerate(d["top_users"], 1):
            n = f"@{u['username']}" if u['username'] else (u['full_name'] or str(u['user_id']))
            t += f"{i}. {n} — <b>${u['earned']:.2f}</b> ({u['cnt']})\n"
    else: t += "<i>нет</i>\n"
    t += "\n<b>Топ-5 операторов:</b>\n"
    if d["top_ops"]:
        for i, o in enumerate(d["top_ops"], 1):
            t += f"{i}. {o['name']} — {o['cnt']} (${o['total_sum']:.2f})\n"
    else: t += "<i>нет</i>\n"
    t += (f"\n<b>Конверсия:</b>\nПринято: <b>{d['accepted']}</b>\nНа проверке: <b>{d['pending']}</b>\n"
          f"Отклонено: <b>{d['rejected']}</b>\nВсего: <b>{d['total']}</b> → <b>{conv:.1f}%</b>\n\n<b>7 дней:</b>\n")
    if d["week"]:
        for w in d["week"]: t += f"{w['d']}: <b>{w['cnt']}</b>\n"
    else: t += "<i>нет</i>"
    await cb.message.edit_text(t, reply_markup=adm_analytics_kb(), disable_web_page_preview=True)
    await cb.answer()


@dp.callback_query(F.data == "adm_active_apps")
async def adm_active_apps(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    apps = await get_all_active_apps()
    if not apps: return await cb.answer("Активных нет.", show_alert=True)
    await cb.message.edit_text(f"<b>Активные ({len(apps)})</b>", reply_markup=None); await cb.answer()
    chunk = ""
    for a in apps:
        st = STATUS_RU.get(a['status'], a['status'])
        v = a['phone_number'] if a['mode'] == 'number' else a['qr_number']
        un = f"@{a['username']}" if a['username'] else (a['full_name'] or a['user_id'])
        chunk += f"<b>#{a['id']}</b> | {a['mode'].upper()} | {v} | {a['op_name']}\n{un} | {st}\n\n"
        if len(chunk) > 3000: await cb.message.answer(chunk); chunk = ""
    if chunk: await cb.message.answer(chunk)


@dp.callback_query(F.data == "adm_export_csv")
async def adm_export_csv(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.answer("Генерирую...")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    apps = await get_full_apps_export()
    buf = io.StringIO(); w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    w.writerow(["# Отчёт по заявкам"]); w.writerow([f"Выгружено: {now}"]); w.writerow([f"Всего: {len(apps)}"]); w.writerow([])
    w.writerow(["ID","UserID","Username","Имя","Режим","Значение","Оператор","Цена ном","Цена QR","Итог","Статус","Причина","Создана","Обработана","Код"])
    tsum = 0.0
    for a in apps:
        (aid,uid,un,fn,mode,val,on,pn,pq,status,rr,cr,pr,code) = a
        fin = pn if mode=='number' else pq
        if status=='accepted': tsum += fin
        w.writerow([aid,uid,un,fn,MODE_RU.get(mode,mode),val,on,f"{pn:.2f}",f"{pq:.2f}",
                    f"{fin:.2f}" if status=='accepted' else "—",STATUS_RU.get(status,status),
                    rr or "—",(cr or "").split('.')[0],(pr or "").split('.')[0] if pr else "—",code or "—"])
    w.writerow([]); w.writerow(["","","","","","","","","ИТОГО:",f"{tsum:.2f}"])
    wds = await get_full_withdrawals_export(); buf2 = io.StringIO(); w2 = csv.writer(buf2)
    w2.writerow(["# Отчёт по выплатам"]); w2.writerow([f"Выгружено: {now}"]); w2.writerow([f"Всего: {len(wds)}"]); w2.writerow([])
    w2.writerow(["ID","UserID","Username","Имя","Сумма","Статус","Причина","Чек","Создана","Завершена"])
    paid = 0.0
    for wd in wds:
        (wid,uid,un,fn,amount,status,rr,link,cr,cp) = wd
        if status=='completed': paid += amount
        sr = {"completed":"Выплачено","pending":"В обработке","cancelled":"Отменено"}.get(status,status)
        w2.writerow([wid,uid,un,fn,f"{amount:.2f}",sr,rr or "—",link or "—",(cr or "").split('.')[0],(cp or "").split('.')[0] if cp else "—"])
    w2.writerow([]); w2.writerow(["","","","ИТОГО:",f"{paid:.2f}"])
    usrs = await get_full_users_export(); buf3 = io.StringIO(); w3 = csv.writer(buf3)
    w3.writerow(["# Отчёт по пользователям"]); w3.writerow([f"Выгружено: {now}"]); w3.writerow([f"Всего: {len(usrs)}"]); w3.writerow([])
    w3.writerow(["UserID","Username","Имя","Баланс","Успешно","Неуспешно","Всего","Реферер","Создан"])
    tb = 0.0
    for u in usrs:
        (uid,un,fn,bal,s,f,ref,cr) = u; tb += bal
        w3.writerow([uid,un,fn,f"{bal:.2f}",s,f,s+f,ref or "—",(cr or "").split('.')[0]])
    w3.writerow([]); w3.writerow(["","","ИТОГО:",f"{tb:.2f}"])
    s = await get_summary_export(); buf4 = io.StringIO(); w4 = csv.writer(buf4)
    w4.writerow(["# Сводка"]); w4.writerow([f"Выгружено: {now}"]); w4.writerow([])
    w4.writerow(["Показатель","Значение"])
    for k, v in [("Юзеров", s["users"]), ("Сумма балансов", f"${s['balance']:.2f}"),
                 ("Всего заявок", s["apps"]), ("Принято", s["accepted"]), ("Отклонено", s["rejected"]),
                 ("Выплат", s["wpaid"]), ("Сумма выплат", f"${s['wsum']:.2f}"),
                 ("В ожидании", s["wpend"]), ("Сумма в ожидании", f"${s['wpend_sum']:.2f}")]:
        w4.writerow([k, v])
    async def send(name, b, cap):
        await cb.message.answer_document(BufferedInputFile(b.getvalue().encode('utf-8-sig'), filename=name), caption=cap)
    await send("summary.csv", buf4, "<b>Сводка</b>")
    await send("applications.csv", buf, "<b>Заявки</b>")
    await send("withdrawals.csv", buf2, "<b>Выплаты</b>")
    await send("users.csv", buf3, "<b>Пользователи</b>")


# ========== LOGS / UNBAN ==========
@dp.callback_query(F.data == "adm_logs")
async def adm_logs(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    logs = await get_admin_logs()
    if not logs: return await cb.answer("Логов нет.", show_alert=True)
    t = "<b>Последние действия:</b>\n\n"
    for l in logs:
        t += f"<b>{l['created_at'].split('.')[0]}</b> | ID {l['admin_id']}\n{l['action']} → {l['target']}\n\n"
    await cb.message.answer(t); await cb.answer()


@dp.callback_query(F.data == "adm_unban_menu")
async def adm_unban_menu(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.set_state(AdminStates.waiting_unban_id)
    await cb.message.answer("ID пользователя для разбана:"); await cb.answer()


@dp.message(AdminStates.waiting_unban_id)
async def adm_unban_process(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    try: uid = int(msg.text.strip())
    except Exception: return await msg.answer("Некорректно.")
    await unban_user(uid); await state.clear()
    await msg.answer(f"{E_OK} Пользователь {uid} разбанен!", reply_markup=admin_panel_kb())


# ========== USER INFO ==========
async def render_user_info(uid):
    u, ta, pnd, pwd, twd = await get_user_info_stats(uid)
    if not u: return "Пользователь не найден.", None
    banned = await is_user_banned(uid)
    t = (f"{E_INF} <b>Карточка</b>\n\n<code>{uid}</code>\n{u['full_name'] or '—'}\n"
         f"{E_LNK} @{u['username'] or '—'}\n\n{E_WAL} Баланс: <b>${u['balance']:.2f}</b>\n"
         f"{E_ORD} Заявок: <b>{ta}</b>\nНа проверке: <b>{pnd}</b>\n"
         f"На выводе: <b>${pwd:.2f}</b>\nВыведено: <b>${twd:.2f}</b>\n"
         f"{E_BL} Забанен: <b>{'Да' if banned else 'Нет'}</b>")
    return t, adm_user_info_kb(uid, banned)


@dp.callback_query(F.data.startswith("adm_user_info:"))
async def adm_user_info(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    uid = int(cb.data.split(":")[1]); t, kb = await render_user_info(uid)
    await cb.message.answer(t, reply_markup=kb); await cb.answer()


@dp.callback_query(F.data.startswith("adm_user_refresh:"))
async def adm_user_refresh(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    uid = int(cb.data.split(":")[1]); t, kb = await render_user_info(uid)
    try: await cb.message.edit_text(t, reply_markup=kb)
    except Exception: await cb.message.answer(t, reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data == "adm_find_user")
async def adm_find_user(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.set_state(AdminStates.waiting_user_id_lookup)
    await cb.message.answer("ID пользователя:"); await cb.answer()


@dp.message(AdminStates.waiting_user_id_lookup)
async def adm_find_user_process(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    try: uid = int(msg.text.strip())
    except Exception: return await msg.answer("Некорректно.")
    await state.clear(); t, kb = await render_user_info(uid)
    await msg.answer(t, reply_markup=kb)


@dp.callback_query(F.data.startswith("adm_ban_user:"))
async def adm_ban_user(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    uid = int(cb.data.split(":")[1])
    await ban_user(uid, "Бан от администратора")
    await add_admin_log(cb.from_user.id, "Забанил", f"ID: {uid}")
    t, kb = await render_user_info(uid)
    try: await cb.message.edit_text(t, reply_markup=kb)
    except Exception: pass
    await cb.answer("Забанен", show_alert=True)


@dp.callback_query(F.data.startswith("adm_unban_user:"))
async def adm_unban_user_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    uid = int(cb.data.split(":")[1]); await unban_user(uid)
    await add_admin_log(cb.from_user.id, "Разбанил", f"ID: {uid}")
    t, kb = await render_user_info(uid)
    try: await cb.message.edit_text(t, reply_markup=kb)
    except Exception: pass
    await cb.answer("Разбанен")


@dp.callback_query(F.data.startswith("adm_add_balance:"))
async def adm_add_balance(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    uid = int(cb.data.split(":")[1])
    await state.set_state(AdminStates.waiting_user_balance_amount)
    await state.update_data(target_user=uid, op="add", info_chat=cb.message.chat.id, info_msg=cb.message.message_id)
    await cb.message.answer(f"Сумма для начисления юзеру <code>{uid}</code>:"); await cb.answer()


@dp.callback_query(F.data.startswith("adm_sub_balance:"))
async def adm_sub_balance(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    uid = int(cb.data.split(":")[1])
    await state.set_state(AdminStates.waiting_user_balance_amount)
    await state.update_data(target_user=uid, op="sub", info_chat=cb.message.chat.id, info_msg=cb.message.message_id)
    await cb.message.answer(f"Сумма для списания у <code>{uid}</code>:"); await cb.answer()


@dp.message(AdminStates.waiting_user_balance_amount)
async def adm_apply_balance(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data(); uid = data.get("target_user"); op = data.get("op")
    ic, im = data.get("info_chat"), data.get("info_msg")
    try:
        amt = float(msg.text.replace(",", "."))
        if amt <= 0: raise ValueError
    except Exception: return await msg.answer("Некорректно.")
    if op == "sub": amt = -amt
    await add_balance(uid, amt)
    await add_admin_log(msg.from_user.id, "Изменил баланс", f"ID {uid}: {amt:+.2f}")
    await state.clear()
    t, kb = await render_user_info(uid)
    try: await bot.edit_message_text(t, chat_id=ic, message_id=im, reply_markup=kb)
    except Exception: await msg.answer(t, reply_markup=kb)
    await msg.answer(f"{E_OK} Баланс изменён на <b>{amt:+.2f}$</b>")


@dp.callback_query(F.data.startswith("adm_user_apps:"))
async def adm_user_apps(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    uid = int(cb.data.split(":")[1])
    apps = await get_user_applications(uid)
    if not apps: return await cb.answer("Заявок нет.", show_alert=True)
    t = f"<b>Заявки юзера {uid}:</b>\n\n"
    for a in apps:
        v = a['phone_number'] if a['mode'] == 'number' else a['qr_number']
        t += f"<b>#{a['id']}</b> | {a['mode'].upper()} | {v} | {STATUS_RU.get(a['status'],a['status'])}\n"
    await cb.message.answer(t); await cb.answer()


# ========== ADMIN WITHDRAWALS ==========
@dp.callback_query(F.data == "adm_withdrawals")
async def adm_withdrawals(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    ws = await get_pending_withdrawals()
    if not ws: return await cb.answer("Нет активных заявок.", show_alert=True)
    await cb.message.edit_text("<b>Заявки на вывод</b>", reply_markup=adm_withdrawals_kb(ws)); await cb.answer()


@dp.callback_query(F.data.startswith("adm_cancel_w:"))
async def adm_cancel_w(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    wid = int(cb.data.split(":")[1]); w = await get_withdrawal(wid)
    if not w or w['status'] != 'pending': return await cb.answer("Обработано.", show_alert=True)
    await cancel_withdrawal(wid)
    await add_admin_log(cb.from_user.id, "Отменил вывод", f"#{wid} (${w['amount']:.2f})")
    try: await bot.send_message(w['user_id'],
        f"<b>Заявка #{wid} отменена.</b>\nСумма ${w['amount']:.2f} не возвращается.")
    except Exception: pass
    await cb.answer("Отменено", show_alert=True)
    ws = await get_pending_withdrawals()
    if not ws: await cb.message.edit_text("<b>Все заявки обработаны!</b>", reply_markup=admin_panel_kb())
    else: await cb.message.edit_reply_markup(reply_markup=adm_withdrawals_kb(ws))


@dp.callback_query(F.data.startswith("adm_pay_w:"))
async def adm_pay_w(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    wid = int(cb.data.split(":")[1]); ws = await get_pending_withdrawals()
    w = next((x for x in ws if x['id'] == wid), None)
    if not w: return await cb.answer("Не найдено.", show_alert=True)
    amt, uid = w['amount'], w['user_id']
    try:
        bal = await get_crypto_balance()
    except Exception as e:
        return await cb.answer(f"Ошибка CryptoPay:\n{e}\n\nИспользуй ручную выплату.", show_alert=True)
    if bal < amt:
        await cb.message.answer(
            f"Недостаточно на CryptoPay.\nТребуется: ${amt:.2f}\nВ наличии: ${bal:.2f}\n\n"
            f"Отметь вручную если выплатил сам:",
            reply_markup=manual_pay_kb(wid))
        return await cb.answer()
    try: link = await create_check(amt, uid)
    except Exception as e: return await cb.answer(f"Ошибка чека: {e}", show_alert=True)
    try: await bot.send_message(uid,
        f"<b>Выплата готова!</b>\n\nСумма: <b>${amt:.2f}</b>\nСсылка: {link}\n\nАктивируй в @CryptoBot.")
    except Exception: await cb.message.answer(f"Не смог написать юзеру {uid}, но чек: {link}")
    await complete_withdrawal(wid, link)
    await add_admin_log(cb.from_user.id, "Выплатил", f"#{wid} ${amt:.2f}")
    try:
        st = await daily_stats_for_admin()
        rep = (f"{E_ST} <b>Сводка за сегодня</b>\n\nПринято: <b>{st['accepted']}</b>\n"
               f"Отклонено: <b>{st['rejected']}</b>\n  Блок: <b>{st['block']}</b>\n  Слет: <b>{st['slet']}</b>\n\n"
               f"Выплат: <b>{st['paid_count']}</b> на <b>${st['paid_sum']:.2f}</b>")
        for a in ADMIN_IDS:
            try: await bot.send_message(a, rep)
            except Exception: pass
    except Exception: pass
    await cb.answer("Выплата отправлена!", show_alert=True)
    ws = await get_pending_withdrawals()
    if not ws: await cb.message.edit_text("<b>Все заявки обработаны!</b>", reply_markup=admin_panel_kb())
    else: await cb.message.edit_reply_markup(reply_markup=adm_withdrawals_kb(ws))


@dp.callback_query(F.data.startswith("adm_manual_pay:"))
async def adm_manual_pay(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    wid = int(cb.data.split(":")[1]); w = await get_withdrawal(wid)
    if not w or w['status'] != 'pending': return await cb.answer("Обработано.", show_alert=True)
    await complete_withdrawal(wid, None)
    await add_admin_log(cb.from_user.id, "Ручная выплата", f"#{wid} ${w['amount']:.2f}")
    try: await bot.send_message(w['user_id'], f"<b>Выплата #{wid} на ${w['amount']:.2f} выполнена.</b>")
    except Exception: pass
    await cb.answer("Отмечено", show_alert=True)
    ws = await get_pending_withdrawals()
    if not ws: await cb.message.edit_text("<b>Все обработаны!</b>", reply_markup=admin_panel_kb())
    else: await cb.message.edit_reply_markup(reply_markup=adm_withdrawals_kb(ws))


# ========== OPERATORS / PRICES / STATS / BROADCAST ==========
@dp.callback_query(F.data == "adm_manage_ops")
async def adm_manage_ops(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    ops = await get_operators()
    await cb.message.edit_text("<b>Операторы:</b>", reply_markup=adm_ops_list_kb(ops)); await cb.answer()


@dp.callback_query(F.data.startswith("adm_op:"))
async def op_edit(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    op = await get_operator(int(cb.data.split(":")[1]))
    await cb.message.edit_text(
        f"<b>{op['name']}</b>\n\n{E_PH} Номер: {'ВКЛ' if op['number_active'] else 'ВЫКЛ'}\n"
        f"QR: {'ВКЛ' if op['qr_active'] else 'ВЫКЛ'}", reply_markup=operator_edit_kb(op))
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_change_name:"))
async def op_change_name(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    oid = int(cb.data.split(":")[1])
    await state.set_state(AdminStates.waiting_new_name); await state.update_data(op_id=oid)
    await cb.message.answer("Новое название:"); await cb.answer()


@dp.message(AdminStates.waiting_new_name)
async def save_new_name(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    if not msg.text: return await msg.answer("Пустое.")
    data = await state.get_data(); oid = data["op_id"]
    await update_operator_name(oid, msg.text.strip()); await state.clear()
    op = await get_operator(oid); await add_admin_log(msg.from_user.id, "Сменил имя", f"{oid} → {msg.text.strip()}")
    await msg.answer(f"{E_OK} Название: <b>{msg.text.strip()}</b>", reply_markup=operator_edit_kb(op))


@dp.callback_query(F.data.startswith("adm_tog:"))
async def op_toggle(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    _, oid, field = cb.data.split(":"); oid = int(oid)
    old = await get_operator(oid); was_off = not old[field]
    await toggle_operator(oid, field); op = await get_operator(oid)
    await cb.message.edit_reply_markup(reply_markup=operator_edit_kb(op)); await cb.answer("Изменено")
    if was_off and op[field]:
        subs = await get_operator_subs(oid)
        if subs:
            for u in subs:
                try: await bot.send_message(u, f"<b>{op['name']}</b> снова в работе!")
                except Exception: pass
            await clear_operator_subs(oid)
            await cb.message.answer(f"Уведомлены {len(subs)} юзеров.")
        await add_admin_log(cb.from_user.id, "Включил оператора", op['name'])


@dp.callback_query(F.data == "adm_start_all")
async def adm_start_all(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await set_setting("auto_work", "1"); await start_all_operators()
    await add_admin_log(cb.from_user.id, "Начать ворк", "Все вкл")
    await cb.answer("Все включены!", show_alert=True)
    ws, we = await get_work_start(), await get_work_end()
    await cb.message.edit_text(f"<b>Админ-панель</b>\n\nАвто ({ws}–{we}) активен.", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "adm_stop_all")
async def adm_stop_all(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await set_setting("auto_work", "0"); await stop_all_operators()
    await add_admin_log(cb.from_user.id, "Стоп-ворк", "Все выкл")
    await cb.answer("Стоп-ворк!", show_alert=True)
    await cb.message.edit_text("<b>Админ-панель</b>\n\nСтоп-ворк. Авто-график отключён.", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "adm_run_payouts")
async def adm_run_payouts(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.answer("Запускаю...", show_alert=True)
    payouts = await get_all_pending_payouts(); cnt = 0
    for app in payouts:
        if not await try_payout(app["id"]): continue
        op = await get_operator(app["operator_id"])
        p = op["price_qr"] if app["mode"] == "qr" else op["price_number"]
        await add_balance(app["user_id"], p)
        try: await bot.send_message(app["user_id"],
            f"{E_OK} <b>Засчитано</b>\n\nНомер: <code>{app['qr_number']}</code>\nЗаказ: <b>#{app['id']}</b>\n\nВыплата переведена.")
        except Exception: pass
        cnt += 1
    await add_admin_log(cb.from_user.id, "Принуд. выплаты", f"Заявок: {cnt}")
    await cb.message.answer(f"{E_OK} Начислено: <b>{cnt}</b>")


@dp.callback_query(F.data == "adm_change_price_mode")
async def adm_change_price_mode(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text("<b>Категория:</b>", reply_markup=adm_price_mode_kb()); await cb.answer()


@dp.callback_query(F.data.startswith("adm_price_mode:"))
async def adm_price_mode(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    mode = cb.data.split(":")[1]; ops = await get_operators()
    await cb.message.edit_text(f"{E_M} <b>Оператор:</b>", reply_markup=adm_price_ops_kb(ops, mode)); await cb.answer()


@dp.callback_query(F.data.startswith("adm_price_op:"))
async def adm_price_op(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    _, oid, mode = cb.data.split(":")
    await state.set_state(AdminStates.waiting_price); await state.update_data(op_id=int(oid), mode=mode)
    await cb.message.answer(f"Новая цена для <b>{'Номер' if mode == 'number' else 'QR'}</b>:"); await cb.answer()


@dp.message(AdminStates.waiting_price)
async def save_price(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    try: p = float(msg.text.replace(",", "."))
    except Exception: return await msg.answer("Некорректно.")
    data = await state.get_data(); field = "price_number" if data["mode"] == "number" else "price_qr"
    await update_operator_price(data["op_id"], field, p); await state.clear()
    op = await get_operator(data["op_id"])
    await add_admin_log(msg.from_user.id, "Сменил цену", f"{op['name']} ({data['mode']}): ${p:.2f}")
    await msg.answer(f"{E_OK} {op['name']} ({data['mode']}): <b>${p:.2f}</b>", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "adm_stats_menu")
async def adm_stats_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text(f"{E_ST} <b>Статистика</b>", reply_markup=adm_stats_menu_kb()); await cb.answer()


@dp.callback_query(F.data == "adm_stats_day")
async def stats_day(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    s = await get_day_stats()
    t = (f"{E_ST} <b>За сегодня</b>\n\n{E_PROF} <b>Юзеры:</b>\n├ Всего: <b>{s['total_users']}</b>\n└ Новых: <b>{s['new_users']}</b>\n\n"
         f"{E_ORD} <b>Заявки:</b>\n├ Принято: <b>{s['accepted']}</b>\n├ Блок: <b>{s['block']}</b>\n"
         f"├ Не скан: <b>{s['slet']}</b>\n├ Прочее: <b>{s['other_rej']}</b>\n└ На проверке: <b>{s['pending']}</b>\n\n"
         f"{E_M} <b>Заработано:</b> <b>${s['acc_sum']:.2f}</b>\n<b>Операторов сдали:</b> {s['active_ops']}\n\n"
         f"{E_WAL} <b>Выплаты:</b>\n├ Завершено: <b>{s['wd_completed']}</b> на <b>${s['wd_completed_sum']:.2f}</b>\n"
         f"├ В обработке: <b>{s['wd_pending']}</b> на <b>${s['wd_pending_sum']:.2f}</b>\n└ Отменено: <b>{s['wd_cancelled']}</b>\n\n"
         f"{E_TOT} <b>Балансы:</b> ${s['total_balance']:.2f}")
    await cb.message.answer(t); await cb.answer()


@dp.callback_query(F.data == "adm_stats_total")
async def stats_total_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    s = await get_total_stats()
    conv = (s['accepted'] / s['total_apps'] * 100) if s['total_apps'] else 0
    t = (f"{E_TOT} <b>За всё время</b>\n\n{E_PROF} <b>Юзеры:</b>\n├ Всего: <b>{s['total_users']}</b>\n└ Балансы: <b>${s['total_balance']:.2f}</b>\n\n"
         f"{E_ORD} <b>Заявки:</b>\n├ Всего: <b>{s['total_apps']}</b>\n├ Принято: <b>{s['accepted']}</b>\n"
         f"├ Блок: <b>{s['block']}</b>\n├ Не скан: <b>{s['slet']}</b>\n├ Всего отклонено: <b>{s['all_rej']}</b>\n"
         f"├ На проверке: <b>{s['pending']}</b>\n└ Конверсия: <b>{conv:.1f}%</b>\n\n"
         f"{E_M} <b>Оборот:</b>\n├ Заработано: <b>${s['acc_sum']:.2f}</b>\n└ Штрафы: <b>${s['fines_sum']:.2f}</b>\n\n"
         f"<b>Операторов сдали:</b> {s['active_ops']}/{s['total_ops']}\n\n"
         f"{E_WAL} <b>Выплаты:</b>\n├ Завершено: <b>{s['wd_completed']}</b> на <b>${s['wd_completed_sum']:.2f}</b>\n"
         f"├ В обработке: <b>{s['wd_pending']}</b> на <b>${s['wd_pending_sum']:.2f}</b>\n└ Отменено: <b>{s['wd_cancelled']}</b>")
    await cb.message.answer(t); await cb.answer()


@dp.callback_query(F.data == "adm_broadcast")
async def broadcast_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.set_state(AdminStates.waiting_broadcast)
    await cb.message.answer(f"{E_BC} Отправь сообщение для рассылки:"); await cb.answer()


@dp.message(AdminStates.waiting_broadcast)
async def do_broadcast(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await state.clear(); ids = await all_user_ids(); sent = 0
    for uid in ids:
        try:
            if msg.photo: await bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.html_text)
            else: await bot.send_message(uid, msg.html_text)
            sent += 1
        except Exception: pass
    await add_admin_log(msg.from_user.id, "Рассылка", f"Доставлено: {sent}")
    await msg.answer(f"{E_OK} Доставлено: {sent}")


# ========== APP DECISIONS ==========
@dp.callback_query(F.data.startswith("adm_accept:"))
async def accept(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    aid = int(cb.data.split(":")[1]); app = await get_application(aid)
    if not app or app["status"] in ('accepted', 'rejected', 'cancelled'): return await cb.answer("Обработано", show_alert=True)
    op = await get_operator(app["operator_id"])
    price = op["price_number"] if app["mode"] == "number" else op["price_qr"]
    if app["mode"] == "number":
        await update_app(aid, status="accepted", awaiting_code=0, processed_at=datetime.utcnow())
        await add_balance(app["user_id"], price)
        try: await bot.send_message(app["user_id"], f"{E_OK} <b>Заявка #{aid} принята!</b>\n{E_M} +${price:.2f}")
        except Exception: pass
    else:
        p_at = (datetime.utcnow() + timedelta(minutes=QR_COOLDOWN_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
        await update_app(aid, status="accepted", awaiting_code=0, payout_at=p_at, processed_at=datetime.utcnow())
        try: await bot.send_message(app["user_id"],
            f"{E_ACC} <b>Номер принят</b>\n\nНомер: <code>{app['qr_number']}</code>\nЗаказ: <b>#{aid}</b>")
        except Exception: pass
    await increment_orders(app["user_id"], True)
    u = await get_user(app["user_id"])
    if u and u["referrer_id"]:
        b = await get_setting_float("ref_bonus", REF_BONUS); await add_balance(u["referrer_id"], b)
        try: await bot.send_message(u["referrer_id"], f"Реф. бонус: <b>+${b:.2f}</b>")
        except Exception: pass
    await add_admin_log(cb.from_user.id, "Принял заявку", f"#{aid} (${price:.2f})")
    await safe_edit_app_message(cb.message, f"{E_OK} ПРИНЯТА",
                                application_admin_kb(aid, app["mode"], "accepted", app["user_id"]))
    await cb.answer("Принято")


@dp.callback_query(F.data.startswith("adm_undo_accept:"))
async def undo_accept(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    aid = int(cb.data.split(":")[1]); app = await get_application(aid)
    if not app or app["status"] != 'accepted': return await cb.answer("Нельзя", show_alert=True)
    op = await get_operator(app["operator_id"])
    price = op["price_number"] if app["mode"] == "number" else op["price_qr"]
    u = await get_user(app["user_id"]); ded = min(price, max(0.0, u["balance"] if u else 0.0))
    if ded > 0: await add_balance(app["user_id"], -ded)
    await update_app(aid, status="pending", payout_at=None, processed_at=None)
    await increment_orders(app["user_id"], True, -1)
    try: await bot.send_message(app["user_id"], f"<b>Заявка #{aid} возвращена.</b>\nСписано: ${ded:.2f}")
    except Exception: pass
    await add_admin_log(cb.from_user.id, "Отменил принятие", f"#{aid}")
    await safe_edit_app_message(cb.message, "ВОЗВРАЩЕНА",
                                application_admin_kb(aid, app["mode"], "pending", app["user_id"]))
    await cb.answer("Возвращено")


@dp.callback_query(F.data.startswith("adm_undo_reject:"))
async def undo_reject(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    aid = int(cb.data.split(":")[1]); app = await get_application(aid)
    if not app or app["status"] != 'rejected': return await cb.answer("Нельзя", show_alert=True)
    await increment_orders(app["user_id"], False, -1)
    if app["mode"] == "qr" and app["reject_reason"] == "block":
        op = await get_operator(app["operator_id"]); u = await get_user(app["user_id"])
        if u: await add_balance(app["user_id"], op["price_qr"])
    await update_app(aid, status="pending", reject_reason=None, processed_at=None)
    try: await bot.send_message(app["user_id"], f"<b>Заявка #{aid} возвращена.</b>")
    except Exception: pass
    await add_admin_log(cb.from_user.id, "Отменил отклонение", f"#{aid}")
    await safe_edit_app_message(cb.message, "ВОЗВРАЩЕНА",
                                application_admin_kb(aid, app["mode"], "pending", app["user_id"]))
    await cb.answer("Возвращено")


@dp.callback_query(F.data.startswith("adm_undo_cancel:"))
async def undo_cancel(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    aid = int(cb.data.split(":")[1]); app = await get_application(aid)
    if not app or app["status"] != 'cancelled': return await cb.answer("Нельзя", show_alert=True)
    await update_app(aid, status="pending", processed_at=None)
    try: await bot.send_message(app["user_id"], f"<b>Заявка #{aid} восстановлена.</b>")
    except Exception: pass
    await add_admin_log(cb.from_user.id, "Восстановил", f"#{aid}")
    await safe_edit_app_message(cb.message, "ВОССТАНОВЛЕНА",
                                application_admin_kb(aid, app["mode"], "pending", app["user_id"]))
    await cb.answer("Восстановлено")


@dp.callback_query(F.data.startswith("adm_cancel:"))
async def cancel_app(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    aid = int(cb.data.split(":")[1]); app = await get_application(aid)
    if not app or app["status"] != 'pending': return await cb.answer("Обработано", show_alert=True)
    await update_app(aid, status="cancelled", processed_at=datetime.utcnow())
    try: await bot.send_message(app["user_id"], f"<b>Заявка #{aid} отменена.</b>")
    except Exception: pass
    await add_admin_log(cb.from_user.id, "Отменил заявку", f"#{aid}")
    await safe_edit_app_message(cb.message, "ОТМЕНЕНА",
                                application_admin_kb(aid, app["mode"], "cancelled", app["user_id"]))
    await cb.answer("Отменено")


@dp.callback_query(F.data.startswith("adm_code:"))
async def request_code(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    aid = int(cb.data.split(":")[1]); app = await get_application(aid)
    await update_app(aid, status="code_requested", awaiting_code=1)
    try: await bot.send_message(app["user_id"],
        f"Админ запросил <b>код</b> для заявки #{aid}.\n\nОтправь код одним сообщением.", reply_markup=user_code_kb())
    except Exception: return await cb.answer("Юзер заблокировал бота", show_alert=True)
    await add_admin_log(cb.from_user.id, "Запросил код", f"#{aid}")
    await safe_edit_app_message(cb.message, "ЗАПРОШЕН КОД",
                                application_admin_kb(aid, app["mode"], "code_requested", app["user_id"]))
    await cb.answer("Запрос отправлен")


@dp.callback_query(F.data.startswith("adm_reject:"))
async def reject(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    aid = int(cb.data.split(":")[1]); app = await get_application(aid)
    if app["mode"] == "number":
        await state.set_state(AdminStates.waiting_reject_reason); await state.update_data(reject_app_id=aid)
        await cb.message.answer(f"Причина для заявки #{aid}:"); await cb.answer()
    else:
        await cb.message.edit_reply_markup(reply_markup=reject_reason_kb(aid)); await cb.answer("Выбери причину")


@dp.message(AdminStates.waiting_reject_reason)
async def process_reject_reason(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data(); aid = data.get("reject_app_id"); await state.clear()
    if not aid or not msg.text: return await msg.answer("Пустая причина.")
    app = await get_application(int(aid))
    if not app or app["status"] in ("rejected", "accepted", "cancelled"): return
    await update_app(aid, status="rejected", awaiting_code=0, reject_reason=msg.text.strip(), processed_at=datetime.utcnow())
    await increment_orders(app["user_id"], False)
    try: await bot.send_message(app["user_id"], f"{E_NO} <b>Заявка #{aid} отклонена.</b>\n\nПричина: {msg.text.strip()}")
    except Exception: pass
    await add_admin_log(msg.from_user.id, "Отклонил заявку", f"#{aid}: {msg.text.strip()}")
    await msg.answer(f"Заявка #{aid} отклонена.")


@dp.callback_query(F.data.startswith("adm_back:"))
async def reject_back(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    aid = int(cb.data.split(":")[1]); app = await get_application(aid)
    await cb.message.edit_reply_markup(reply_markup=application_admin_kb(aid, app["mode"], app["status"], app["user_id"]))
    await cb.answer()


@dp.callback_query(F.data.startswith("adm_reason:"))
async def reject_with_reason(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    _, aid, reason = cb.data.split(":"); aid = int(aid); app = await get_application(aid)
    if not app or app["status"] in ("rejected", "accepted", "cancelled"): return
    await update_app(aid, status="rejected", awaiting_code=0, reject_reason=reason, processed_at=datetime.utcnow())
    await increment_orders(app["user_id"], False)
    op = await get_operator(app["operator_id"]); phone = app["qr_number"]
    if reason == "block":
        u = await get_user(app["user_id"]); fine = min(op["price_qr"], max(0.0, u["balance"] if u else 0.0))
        if fine > 0: await add_balance(app["user_id"], -fine)
        try: await bot.send_message(app["user_id"], f"{E_BL} <b>Ваш номер {phone} заблокирован.</b>\nСписано: <b>${fine:.2f}</b>")
        except Exception: pass
    elif reason == "slet":
        try: await bot.send_message(app["user_id"], f"{E_NO} <b>Ваш номер {phone} — Не скан.</b>")
        except Exception: pass
    rl = {"block": "Блок", "slet": "Не скан"}.get(reason, reason)
    await add_admin_log(cb.from_user.id, "Отклонил (QR)", f"#{aid}: {rl}")
    await safe_edit_app_message(cb.message, f"ОТКЛОНЕНА ({rl})",
                                application_admin_kb(aid, app["mode"], "rejected", app["user_id"]))
    await cb.answer("Отклонено")


# ========== WORKERS ==========
async def payout_worker():
    while True:
        try:
            if not await is_auto_payout():
                await asyncio.sleep(30); continue
            for app in await pending_payouts():
                if not await try_payout(app["id"]): continue
                op = await get_operator(app["operator_id"])
                p = op["price_qr"] if app["mode"] == "qr" else op["price_number"]
                await add_balance(app["user_id"], p)
                try: await bot.send_message(app["user_id"],
                    f"{E_OK} <b>Засчитано</b>\n\nНомер: <code>{app['qr_number']}</code>\nЗаказ: <b>#{app['id']}</b>")
                except Exception: pass
        except Exception: logging.exception("payout_worker")
        await asyncio.sleep(30)


async def work_scheduler():
    while True:
        try:
            if await is_maintenance():
                await asyncio.sleep(60); continue
            if await get_setting("auto_work") == "1":
                now_msk = datetime.utcnow() + timedelta(hours=3)
                ws_s, we_s = await get_work_start(), await get_work_end()
                try:
                    wh, wm = [int(x) for x in ws_s.split(":")]; eh, em = [int(x) for x in we_s.split(":")]
                except Exception: wh, wm, eh, em = 6, 0, 19, 0
                cur = now_msk.hour * 60 + now_msk.minute; s = wh * 60 + wm; e = eh * 60 + em
                in_w = (s <= cur < e) if s < e else (cur >= s or cur < e)
                ops = await get_operators(); any_on = any(op["number_active"] or op["qr_active"] for op in ops)
                if in_w and not any_on:
                    await start_all_operators(); logging.info("Авто: включены")
                elif not in_w and any_on:
                    await stop_all_operators(); logging.info("Авто: выключены")
        except Exception: logging.exception("work_scheduler")
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