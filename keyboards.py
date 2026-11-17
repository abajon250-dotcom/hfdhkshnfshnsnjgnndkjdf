from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from config import CHANNEL_LINK, SUPPORT_LINK

E_PROFILE = "5258011929993026890"
E_WALLET = "5258204546391351475"
E_STATS = "5258330865674494479"
E_SUCCESS = "5260416304224936047"
E_FAIL = "5260342697075416641"
E_TOTAL = "5258057130228849960"
E_CALENDAR = "5258105663359294787"
E_LINK = "5260730055880876557"
E_START_WORK = "5258337316715373336"
E_MONEY = "5258368777350816286"
E_BLOCK = "5258318620722733379"
E_NUM_ACCEPTED = "5258501105293205250"
E_PHONE = "5258337316715373336"
E_ORDER = "5258461531464539536"
E_NOT_ACCEPT = "5260249440450520061"
E_BROADCAST = "5258089153505009279"
E_DOWN = "5231102735817918643"
E_SUPPORT = "5316727448644103237"
E_SWITCH = "5226513232549664618"
E_TICKET_NEW = "5775937998948404844"
E_TICKET_MY = "5875462364110787088"
E_TICKET_REPLY = "5832251986635920010"
E_TICKET_SOLVED = "5825794181183836432"
E_INFO = "5879770735999717115"
E_BAN = "5872829476143894491"
E_UNBAN = "5776375003280838798"
E_ADD_BAL = "5775937998948404844"
E_SUB_BAL = "5807405618008433289"
E_HISTORY = "6021454607513819417"
E_SETTINGS = "6021582331251268218"
E_CLOCK = "6034898821517940846"


def sub_kb():
    kb = InlineKeyboardBuilder()
    if CHANNEL_LINK: kb.button(text="Подписаться", url=CHANNEL_LINK, icon_custom_emoji_id=E_LINK)
    kb.button(text="Проверить подписку", callback_data="check_sub", icon_custom_emoji_id=E_SUCCESS)
    return kb.as_markup()


def main_menu_kb(is_admin: bool):
    kb = ReplyKeyboardBuilder()
    kb.button(text="Начать работу", icon_custom_emoji_id=E_START_WORK)
    kb.button(text="Мой профиль", icon_custom_emoji_id=E_PROFILE)
    kb.button(text="Поддержка", icon_custom_emoji_id=E_SUPPORT)
    if is_admin:
        kb.button(text="Админ-панель", icon_custom_emoji_id=E_SETTINGS); kb.adjust(2, 1, 1)
    else: kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True)


def operators_kb(operators, mode, active_category='regular'):
    kb = InlineKeyboardBuilder()
    if mode == "number":
        kb.button(text="Режим сдачи: Номер", callback_data="mode:qr", icon_custom_emoji_id=E_SWITCH)
    else:
        kb.button(text="Режим сдачи: Готовый QR", callback_data="mode:number", icon_custom_emoji_id=E_SWITCH)
    if mode == 'qr':
        kb.button(text="Обычные", callback_data=f"cat:{mode}:regular", **({"style": "primary"} if active_category == 'regular' else {}))
        kb.button(text="Салон", callback_data=f"cat:{mode}:salon", **({"style": "primary"} if active_category == 'salon' else {}))
    field = "number_active" if mode == "number" else "qr_active"
    price_field = "price_number" if mode == "number" else "price_qr"
    has_ops = False
    for op in operators:
        if mode == 'qr' and op["category"] != active_category: continue
        p = op[price_field]
        btn = f"{op['name']} | {p:.0f}$" if p % 1 == 0 else f"{op['name']} | {p:.2f}$"
        kw = {"icon_custom_emoji_id": op["emoji_id"]} if op["emoji_id"] else {}
        if op[field]: kb.button(text=btn, callback_data=f"op:{mode}:{op['id']}", **kw)
        else: kb.button(text=btn, callback_data=f"op_disabled:{op['id']}", style="danger", **kw)
        has_ops = True
    if not has_ops: kb.button(text="В этой категории пока нет операторов", callback_data="ignore")
    if mode == 'qr': kb.adjust(1, 2, 2)
    else: kb.adjust(1, 2)
    return kb.as_markup()


def profile_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Вывести средства", callback_data="withdraw", icon_custom_emoji_id=E_WALLET)
    kb.button(text="Журнал заявок", callback_data="audit_log", icon_custom_emoji_id=E_ORDER)
    kb.button(text="История выплат", callback_data="withdraw_history", icon_custom_emoji_id=E_MONEY)
    kb.adjust(1, 2)
    return kb.as_markup()


def leaderboard_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Обновить", callback_data="leaderboard", icon_custom_emoji_id=E_STATS); kb.adjust(1)
    return kb.as_markup()


def user_code_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Написать код", callback_data="user_write_code")
    kb.button(text="Отмена", callback_data="user_cancel_code", style="danger")
    kb.adjust(2)
    return kb.as_markup()


def support_menu_kb(urgent_link: str | None = None):
    kb = InlineKeyboardBuilder()
    kb.button(text="Создать обращение", callback_data="support_new", icon_custom_emoji_id=E_TICKET_NEW)
    kb.button(text="Мои обращения", callback_data="support_my", icon_custom_emoji_id=E_TICKET_MY)
    if urgent_link: kb.button(text="Срочная связь", url=urgent_link, icon_custom_emoji_id=E_LINK)
    kb.adjust(1)
    return kb.as_markup()


def admin_ticket_action_kb(ticket_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="Ответить", callback_data=f"adm_reply_ticket:{ticket_id}", icon_custom_emoji_id=E_TICKET_REPLY)
    kb.button(text="Закрыть", callback_data=f"adm_close_ticket:{ticket_id}", style="danger")
    kb.adjust(2)
    return kb.as_markup()


def user_ticket_action_kb(ticket_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="Ответить", callback_data=f"user_reply_ticket:{ticket_id}", icon_custom_emoji_id=E_TICKET_REPLY)
    kb.button(text="Проблема решена", callback_data=f"user_close_ticket:{ticket_id}", style="success", icon_custom_emoji_id=E_TICKET_SOLVED)
    kb.adjust(2)
    return kb.as_markup()


def application_admin_kb(app_id, mode, status='pending', user_id=None):
    kb = InlineKeyboardBuilder()
    if status in ('pending', 'code_requested', 'code_sent'):
        kb.button(text="Принять", callback_data=f"adm_accept:{app_id}", style="success", icon_custom_emoji_id=E_SUCCESS)
        if mode == "number": kb.button(text="Запросить код", callback_data=f"adm_code:{app_id}", style="primary")
        kb.button(text="Отклонить", callback_data=f"adm_reject:{app_id}", style="danger", icon_custom_emoji_id=E_FAIL)
        kb.button(text="Отмена", callback_data=f"adm_cancel:{app_id}")
        if user_id: kb.button(text="Инфо о юзере", callback_data=f"adm_user_info:{user_id}", icon_custom_emoji_id=E_INFO)
        kb.adjust(2, 1, 1, 1)
    elif status == 'accepted':
        kb.button(text="Отменить принятие", callback_data=f"adm_undo_accept:{app_id}", style="danger")
        if user_id: kb.button(text="Инфо о юзере", callback_data=f"adm_user_info:{user_id}", icon_custom_emoji_id=E_INFO)
        kb.adjust(1, 1)
    elif status == 'rejected':
        kb.button(text="Вернуть на проверку", callback_data=f"adm_undo_reject:{app_id}", style="primary")
        if user_id: kb.button(text="Инфо о юзере", callback_data=f"adm_user_info:{user_id}", icon_custom_emoji_id=E_INFO)
        kb.adjust(1, 1)
    elif status == 'cancelled':
        kb.button(text="Восстановить заявку", callback_data=f"adm_undo_cancel:{app_id}", style="primary")
        if user_id: kb.button(text="Инфо о юзере", callback_data=f"adm_user_info:{user_id}", icon_custom_emoji_id=E_INFO)
        kb.adjust(1, 1)
    return kb.as_markup()


def reject_reason_kb(app_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="Не скан", callback_data=f"adm_reason:{app_id}:slet", style="danger")
    kb.button(text="Блок", callback_data=f"adm_reason:{app_id}:block", style="danger", icon_custom_emoji_id=E_BLOCK)
    kb.button(text="Назад", callback_data=f"adm_back:{app_id}")
    kb.adjust(2, 1)
    return kb.as_markup()


def admin_panel_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Управление операторами", callback_data="adm_manage_ops")
    kb.button(text="Настройки", callback_data="adm_settings", icon_custom_emoji_id=E_SETTINGS)
    kb.button(text="Инфо о юзере", callback_data="adm_find_user", icon_custom_emoji_id=E_INFO)
    kb.button(text="Активные заявки", callback_data="adm_active_apps", icon_custom_emoji_id=E_ORDER)
    kb.button(text="Аналитика", callback_data="adm_analytics", icon_custom_emoji_id=E_STATS)
    kb.button(text="Сменить цену", callback_data="adm_change_price_mode", icon_custom_emoji_id=E_WALLET)
    kb.button(text="Статистика", callback_data="adm_stats_menu", icon_custom_emoji_id=E_TOTAL)
    kb.button(text="Рассылка", callback_data="adm_broadcast", icon_custom_emoji_id=E_BROADCAST)
    kb.button(text="Заявки на вывод", callback_data="adm_withdrawals", icon_custom_emoji_id=E_MONEY)
    kb.button(text="Экспорт базы (CSV)", callback_data="adm_export_csv", icon_custom_emoji_id=E_HISTORY)
    kb.button(text="Логи действий", callback_data="adm_logs", icon_custom_emoji_id=E_HISTORY)
    kb.button(text="Разбанить юзера", callback_data="adm_unban_menu", icon_custom_emoji_id=E_UNBAN)
    kb.button(text="Начать ворк", callback_data="adm_start_all", style="success", icon_custom_emoji_id=E_SUCCESS)
    kb.button(text="Стоп-ворк", callback_data="adm_stop_all", style="danger", icon_custom_emoji_id=E_NOT_ACCEPT)
    kb.button(text="Тех.работы", callback_data="adm_maintenance", icon_custom_emoji_id=E_NOT_ACCEPT)
    kb.button(text="Закрыть", callback_data="close_admin", icon_custom_emoji_id=E_FAIL)
    kb.adjust(2, 1, 1, 1, 1, 2, 1, 2, 2, 2, 1, 1)
    return kb.as_markup()


def adm_settings_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Мин. вывод", callback_data="adm_set_min", icon_custom_emoji_id=E_MONEY)
    kb.button(text="Время работы", callback_data="adm_set_hours", icon_custom_emoji_id=E_CLOCK)
    kb.button(text="Срочная связь", callback_data="adm_set_urgent", icon_custom_emoji_id=E_LINK)
    kb.button(text="Авто-выплаты", callback_data="adm_set_autopayout", icon_custom_emoji_id=E_WALLET)
    kb.button(text="Назад", callback_data="admin_panel")
    kb.adjust(2, 1, 1, 1)
    return kb.as_markup()


def adm_hours_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Начало ворка", callback_data="adm_set_start", icon_custom_emoji_id=E_CLOCK)
    kb.button(text="Конец ворка", callback_data="adm_set_end", icon_custom_emoji_id=E_CLOCK)
    kb.button(text="Назад", callback_data="adm_settings")
    kb.adjust(2, 1)
    return kb.as_markup()


def adm_maintenance_kb(is_on: bool):
    kb = InlineKeyboardBuilder()
    if is_on: kb.button(text="Выключить тех.работы", callback_data="adm_toggle_maintenance", style="success", icon_custom_emoji_id=E_SUCCESS)
    else: kb.button(text="Включить тех.работы", callback_data="adm_toggle_maintenance", style="danger", icon_custom_emoji_id=E_NOT_ACCEPT)
    kb.button(text="Назад", callback_data="admin_panel")
    kb.adjust(1, 1)
    return kb.as_markup()


def adm_analytics_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Обновить", callback_data="adm_analytics", icon_custom_emoji_id=E_STATS)
    kb.button(text="Назад", callback_data="admin_panel")
    kb.adjust(2)
    return kb.as_markup()


def adm_notify_operator_kb(op_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="Уведомить о включении", callback_data=f"notify_op:{op_id}"); kb.adjust(1)
    return kb.as_markup()


def adm_withdrawals_kb(withdrawals):
    kb = InlineKeyboardBuilder()
    for w in withdrawals:
        kb.button(text=f"Выплатить #{w['id']} (${w['amount']:.2f})", callback_data=f"adm_pay_w:{w['id']}")
        kb.button(text=f"Отменить #{w['id']}", callback_data=f"adm_cancel_w:{w['id']}", style="danger")
    kb.button(text="Назад", callback_data="admin_panel")
    kb.adjust(2)
    return kb.as_markup()


def manual_pay_kb(w_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="Отметить выплаченным", callback_data=f"adm_manual_pay:{w_id}", style="success", icon_custom_emoji_id=E_SUCCESS)
    kb.button(text="Отмена", callback_data="admin_panel")
    kb.adjust(2)
    return kb.as_markup()


def withdraw_history_checks_kb(items):
    kb = InlineKeyboardBuilder()
    has = False
    for w in items:
        try: link = w['check_link']
        except (KeyError, IndexError): link = None
        if w['status'] == 'completed' and link:
            kb.button(text=f"Чек #{w['id']} (${w['amount']:.2f})", url=link, icon_custom_emoji_id=E_LINK); has = True
    if not has: return None
    kb.adjust(1)
    return kb.as_markup()


def adm_user_info_kb(user_id, is_banned):
    kb = InlineKeyboardBuilder()
    if is_banned: kb.button(text="Разбанить", callback_data=f"adm_unban_user:{user_id}", style="success", icon_custom_emoji_id=E_UNBAN)
    else: kb.button(text="Забанить", callback_data=f"adm_ban_user:{user_id}", style="danger", icon_custom_emoji_id=E_BAN)
    kb.button(text="Начислить", callback_data=f"adm_add_balance:{user_id}", style="success", icon_custom_emoji_id=E_ADD_BAL)
    kb.button(text="Списать", callback_data=f"adm_sub_balance:{user_id}", style="danger", icon_custom_emoji_id=E_SUB_BAL)
    kb.button(text="История заявок", callback_data=f"adm_user_apps:{user_id}", icon_custom_emoji_id=E_HISTORY)
    kb.button(text="Обновить", callback_data=f"adm_user_refresh:{user_id}", icon_custom_emoji_id=E_INFO)
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def adm_price_mode_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Номер", callback_data="adm_price_mode:number", icon_custom_emoji_id=E_PHONE)
    kb.button(text="QR", callback_data="adm_price_mode:qr", icon_custom_emoji_id=E_SWITCH)
    kb.button(text="Назад", callback_data="admin_panel")
    kb.adjust(2, 1)
    return kb.as_markup()


def adm_price_ops_kb(operators, mode):
    kb = InlineKeyboardBuilder()
    for op in operators:
        kb.button(text=op['name'], callback_data=f"adm_price_op:{op['id']}:{mode}", **({"icon_custom_emoji_id": op["emoji_id"]} if op["emoji_id"] else {}))
    kb.button(text="Назад", callback_data="adm_change_price_mode")
    kb.adjust(2)
    return kb.as_markup()


def operator_edit_kb(op):
    kb = InlineKeyboardBuilder()
    kb.button(text="Номер вкл" if op["number_active"] else "Номер выкл", callback_data=f"adm_tog:{op['id']}:number_active", icon_custom_emoji_id=E_PHONE)
    kb.button(text="QR вкл" if op["qr_active"] else "QR выкл", callback_data=f"adm_tog:{op['id']}:qr_active", icon_custom_emoji_id=E_SWITCH)
    kb.button(text="Изменить название", callback_data=f"adm_change_name:{op['id']}")
    kb.button(text="Назад", callback_data="adm_manage_ops")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def adm_ops_list_kb(operators):
    kb = InlineKeyboardBuilder()
    for op in operators:
        kb.button(text=op['name'], callback_data=f"adm_op:{op['id']}", **({"icon_custom_emoji_id": op["emoji_id"]} if op["emoji_id"] else {}))
    kb.button(text="Назад", callback_data="admin_panel")
    kb.adjust(2)
    return kb.as_markup()


def adm_stats_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="За сегодня", callback_data="adm_stats_day", icon_custom_emoji_id=E_CALENDAR)
    kb.button(text="За всё время", callback_data="adm_stats_total", icon_custom_emoji_id=E_TOTAL)
    kb.button(text="Назад", callback_data="admin_panel")
    kb.adjust(2, 1)
    return kb.as_markup()
