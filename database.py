import asyncpg
from datetime import datetime
from config import DATABASE_URL

pool = None


async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as conn:
        # Таблица пользователей
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                balance DOUBLE PRECISION DEFAULT 0,
                referrer_id BIGINT,
                successful_orders INTEGER DEFAULT 0,
                failed_orders INTEGER DEFAULT 0,
                last_reject_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # Операторы
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS operators (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                emoji_id TEXT,
                price_number DOUBLE PRECISION DEFAULT 1.0,
                price_qr DOUBLE PRECISION DEFAULT 1.5,
                supports_number INTEGER DEFAULT 1,
                supports_qr INTEGER DEFAULT 1,
                number_active INTEGER DEFAULT 1,
                qr_active INTEGER DEFAULT 1,
                category TEXT DEFAULT 'regular'
            );
        ''')
        # Заявки
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                operator_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                phone_number TEXT,
                qr_photo_id TEXT,
                qr_number TEXT,
                code TEXT,
                awaiting_code INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                reject_reason TEXT,
                payout_at TIMESTAMP,
                admin_chat_id BIGINT,
                admin_message_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            );
        ''')
        # Тикеты
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                message TEXT,
                status TEXT DEFAULT 'open',
                reply TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # Выплаты
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount DOUBLE PRECISION,
                status TEXT DEFAULT 'pending',
                check_url TEXT,
                reject_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # Баны
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id BIGINT PRIMARY KEY,
                reason TEXT,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # Логи
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id SERIAL PRIMARY KEY,
                admin_id BIGINT,
                action TEXT,
                target TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # Подписки на операторов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS operator_subs (
                user_id BIGINT,
                operator_id INTEGER,
                PRIMARY KEY(user_id, operator_id)
            );
        ''')
        # Настройки (мин. вывод, график и т.д.)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        ''')

        # Дефолтные настройки
        await conn.execute("INSERT INTO settings (key, value) VALUES ('min_withdraw', '5.0') ON CONFLICT DO NOTHING;")
        await conn.execute("INSERT INTO settings (key, value) VALUES ('work_start', '06:00') ON CONFLICT DO NOTHING;")
        await conn.execute("INSERT INTO settings (key, value) VALUES ('work_end', '19:00') ON CONFLICT DO NOTHING;")
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES ('support_link', 'https://t.me/your_support') ON CONFLICT DO NOTHING;")

        # Дефолтные операторы
        count = await conn.fetchval("SELECT COUNT(*) FROM operators")
        if count == 0:
            ops = [
                ("Сбер", "5310200356779633554", 18.00, 21.00, 1, 1, 1, 1, "regular"),
                ("МегаФон", "5307580065951819775", 10.00, 16.00, 1, 1, 1, 1, "regular"),
                ("МТС", "5307795879468507258", 15.00, 15.00, 1, 1, 1, 1, "regular"),
                ("Т-Мобайл", "5309887043210356963", 15.00, 20.00, 1, 1, 1, 1, "regular"),
                ("Билайн", "5307627108728613978", 20.00, 19.00, 1, 1, 1, 1, "regular"),
                ("Т2", "5308014437469299183", 20.00, 20.00, 0, 1, 0, 1, "regular"),
                ("ВТБ", "5307905048947239694", 35.00, 35.00, 0, 1, 0, 1, "regular"),
                ("Альфа", "5307502816670035367", 50.00, 50.00, 0, 1, 0, 1, "regular"),
                ("Миранда", "5426865017297347918", 30.00, 30.00, 0, 1, 0, 1, "regular"),
                ("Волна", "5427099170324395438", 17.00, 17.00, 0, 1, 0, 1, "regular"),
                ("Добросвязь", "5429163636549528047", 22.00, 22.00, 0, 1, 0, 1, "regular"),
                ("Газпромбанк", "5307851495000024414", 35.00, 35.00, 0, 1, 0, 1, "regular"),
            ]
            for name, eid, p_num, p_qr, s_num, s_qr, n_act, q_act, cat in ops:
                await conn.execute(
                    "INSERT INTO operators (name, emoji_id, price_number, price_qr, supports_number, supports_qr, number_active, qr_active, category) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                    name, eid, p_num, p_qr, s_num, s_qr, n_act, q_act, cat
                )


# --- НАСТРОЙКИ ---
async def get_setting(key):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT value FROM settings WHERE key = $1", key)


async def set_setting(key, value):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            key, value)


# --- ПОЛЬЗОВАТЕЛИ ---
async def get_user(user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)


async def create_user(user_id, username, full_name, referrer_id=None):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, username, full_name, referrer_id) VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username, full_name = EXCLUDED.full_name
        ''', user_id, username, full_name, referrer_id)


async def add_balance(user_id, amount):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, user_id)


async def update_last_reject(user_id):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_reject_time = NOW() WHERE user_id = $1", user_id)


async def increment_orders(user_id, success: bool, amount: int = 1):
    field = "successful_orders" if success else "failed_orders"
    async with pool.acquire() as conn:
        await conn.execute(f"UPDATE users SET {field} = GREATEST(0, {field} + $1) WHERE user_id = $2", amount, user_id)


# --- ОПЕРАТОРЫ ---
async def get_operators():
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM operators ORDER BY id")


async def get_operator(op_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM operators WHERE id = $1", op_id)


async def update_operator_price(op_id, field, value):
    async with pool.acquire() as conn:
        await conn.execute(f"UPDATE operators SET {field} = $1 WHERE id = $2", value, op_id)


async def toggle_operator(op_id, field):
    async with pool.acquire() as conn:
        await conn.execute(f"UPDATE operators SET {field} = 1 - {field} WHERE id = $1", op_id)


async def set_all_operators(active: bool):
    val = 1 if active else 0
    async with pool.acquire() as conn:
        await conn.execute("UPDATE operators SET number_active = $1, qr_active = $1", val)


# --- ЗАЯВКИ ---
async def check_duplicate_number(mode, number):
    async with pool.acquire() as conn:
        if mode == "number":
            res = await conn.fetchval(
                "SELECT COUNT(*) FROM applications WHERE mode='number' AND phone_number=$1 AND status IN ('pending', 'accepted', 'code_requested', 'code_sent')",
                number)
        else:
            res = await conn.fetchval(
                "SELECT COUNT(*) FROM applications WHERE mode='qr' AND qr_number=$1 AND status IN ('pending', 'accepted', 'code_requested', 'code_sent')",
                number)
        return res > 0


async def create_application(user_id, operator_id, mode, phone_number=None, qr_photo_id=None, qr_number=None):
    async with pool.acquire() as conn:
        app_id = await conn.fetchval('''
            INSERT INTO applications (user_id, operator_id, mode, phone_number, qr_photo_id, qr_number) 
            VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
        ''', user_id, operator_id, mode, phone_number, qr_photo_id, qr_number)
        return app_id


async def set_admin_message(app_id, chat_id, msg_id):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE applications SET admin_chat_id = $1, admin_message_id = $2 WHERE id = $3", chat_id,
                           msg_id, app_id)


async def get_application(app_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM applications WHERE id = $1", app_id)


async def update_app(app_id, **kwargs):
    if not kwargs: return
    keys = list(kwargs.keys())
    vals = list(kwargs.values())
    set_clause = ", ".join([f"{k} = ${i + 1}" for i, k in enumerate(keys)])
    async with pool.acquire() as conn:
        await conn.execute(f"UPDATE applications SET {set_clause} WHERE id = ${len(vals) + 1}", *vals, app_id)


async def get_app_awaiting_code(user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM applications WHERE user_id=$1 AND awaiting_code=1 AND status='code_requested' ORDER BY id DESC LIMIT 1",
            user_id)


async def pending_payouts():
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM applications WHERE status='accepted' AND payout_at IS NOT NULL AND payout_at <= NOW()")


async def try_payout(app_id):
    async with pool.acquire() as conn:
        res = await conn.execute(
            "UPDATE applications SET payout_at = NULL WHERE id = $1 AND status = 'accepted' AND payout_at IS NOT NULL",
            app_id)
        return res == "UPDATE 1"


# --- ВЫПЛАТЫ ---
async def get_pending_withdrawn(user_id):
    async with pool.acquire() as conn:
        res = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE user_id=$1 AND status='pending'", user_id)
        return float(res)


async def get_total_withdrawn(user_id):
    async with pool.acquire() as conn:
        res = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE user_id=$1 AND status='completed'", user_id)
        return float(res)


async def get_total_fines(user_id):
    async with pool.acquire() as conn:
        res = await conn.fetchval('''
            SELECT COALESCE(SUM(o.price_qr), 0) FROM applications a
            JOIN operators o ON o.id = a.operator_id
            WHERE a.user_id = $1 AND a.mode='qr' AND a.status='rejected' AND a.reject_reason='block'
        ''', user_id)
        return float(res)


async def pending_amount(user_id):
    async with pool.acquire() as conn:
        res = await conn.fetchval('''
            SELECT COALESCE(SUM(CASE WHEN a.mode='number' THEN o.price_number ELSE o.price_qr END), 0)
            FROM applications a JOIN operators o ON o.id = a.operator_id
            WHERE a.user_id = $1 AND (a.status IN ('pending', 'code_requested', 'code_sent') OR (a.status='accepted' AND a.payout_at IS NOT NULL AND a.payout_at > NOW()))
        ''', user_id)
        return float(res)


async def create_withdrawal(user_id, amount):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO withdrawals (user_id, amount) VALUES ($1, $2)", user_id, amount)
        await conn.execute("UPDATE users SET balance = balance - $1 WHERE user_id = $2", amount, user_id)


async def get_pending_withdrawals():
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM withdrawals WHERE status='pending'")


async def complete_withdrawal(w_id, check_url):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE withdrawals SET status='completed', check_url=$1 WHERE id=$2", check_url, w_id)


async def cancel_withdrawal(w_id, reason="Отменено администратором"):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE withdrawals SET status='cancelled', reject_reason=$1 WHERE id=$2", reason, w_id)


async def get_user_withdrawals(user_id):
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM withdrawals WHERE user_id=$1 ORDER BY id DESC LIMIT 10", user_id)


# --- СТАТИСТИКА ---
async def stats_today():
    async with pool.acquire() as conn:
        accepted = await conn.fetchval(
            "SELECT COUNT(*) FROM applications WHERE status='accepted' AND date(processed_at) = CURRENT_DATE")
        rejected = await conn.fetchval(
            "SELECT COUNT(*) FROM applications WHERE status='rejected' AND date(processed_at) = CURRENT_DATE")
        total = await conn.fetchval('''
            SELECT COALESCE(SUM(CASE WHEN a.mode='number' THEN o.price_number ELSE o.price_qr END), 0)
            FROM applications a JOIN operators o ON o.id = a.operator_id 
            WHERE a.status='accepted' AND date(a.processed_at) = CURRENT_DATE
        ''')
        return accepted, rejected, float(total)


# --- БАНЫ ---
async def ban_user(user_id):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO banned_users (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)


async def unban_user(user_id):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM banned_users WHERE user_id = $1", user_id)


async def is_user_banned(user_id):
    async with pool.acquire() as conn:
        res = await conn.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", user_id)
        return res is not None


# --- ТИКЕТЫ ---
async def create_ticket(user_id, message):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO tickets (user_id, message) VALUES ($1, $2)", user_id, message)


async def get_user_tickets(user_id):
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM tickets WHERE user_id=$1 ORDER BY id DESC", user_id)


async def get_ticket(ticket_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM tickets WHERE id=$1", ticket_id)


async def reply_ticket(ticket_id, reply):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE tickets SET reply=$1 WHERE id=$2", reply, ticket_id)


async def close_ticket(ticket_id):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE tickets SET status='closed' WHERE id=$1", ticket_id)


async def all_user_ids():
    async with pool.acquire() as conn:
        records = await conn.fetch("SELECT user_id FROM users")
        return [r['user_id'] for r in records]