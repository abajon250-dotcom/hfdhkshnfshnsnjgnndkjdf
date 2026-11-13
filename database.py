import aiosqlite

DB_PATH = "bot.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, balance REAL DEFAULT 0,
            referrer_id INTEGER, successful_orders INTEGER DEFAULT 0, failed_orders INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS operators (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, emoji_id TEXT,
            price_number REAL DEFAULT 1.0, price_qr REAL DEFAULT 1.5,
            supports_number INTEGER DEFAULT 1, supports_qr INTEGER DEFAULT 1,
            number_active INTEGER DEFAULT 1, qr_active INTEGER DEFAULT 1,
            category TEXT DEFAULT 'regular'
        );
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, operator_id INTEGER NOT NULL,
            mode TEXT NOT NULL, phone_number TEXT, qr_photo_id TEXT, qr_number TEXT, code TEXT,
            awaiting_code INTEGER DEFAULT 0, status TEXT DEFAULT 'pending', reject_reason TEXT,
            payout_at TIMESTAMP, admin_chat_id INTEGER, admin_message_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, processed_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, message TEXT,
            status TEXT DEFAULT 'open', reply TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount REAL,
            status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY, reason TEXT, banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, target TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS operator_subs (
            user_id INTEGER, operator_id INTEGER, PRIMARY KEY(user_id, operator_id)
        );
        """)

        cur = await db.execute("SELECT COUNT(*) FROM operators")
        if (await cur.fetchone())[0] == 0:
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
                ("Билайн Салон", "5307627108728613978", 21.00, 21.00, 0, 1, 0, 1, "salon"),
                ("МТС Салон", "5307795879468507258", 22.00, 22.00, 0, 1, 0, 1, "salon"),
                ("МегаФон Салон", "5307580065951819775", 21.00, 21.00, 0, 1, 0, 1, "salon"),
                ("Т2 Салон", "5308014437469299183", 22.00, 22.00, 0, 1, 0, 1, "salon"),
            ]
            for name, eid, p_num, p_qr, s_num, s_qr, n_act, q_act, cat in ops:
                await db.execute(
                    "INSERT INTO operators (name, emoji_id, price_number, price_qr, supports_number, supports_qr, number_active, qr_active, category) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, eid, p_num, p_qr, s_num, s_qr, n_act, q_act, cat)
                )
        await db.commit()


async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as c:
            return await c.fetchone()


async def create_user(user_id, username, full_name, referrer_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, full_name, referrer_id) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name
        """, (user_id, username, full_name, referrer_id))
        await db.commit()


async def add_balance(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
        await db.commit()


async def increment_orders(user_id, success: bool, amount: int = 1):
    field = "successful_orders" if success else "failed_orders"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {field} = MAX(0, {field} + ?) WHERE user_id=?", (amount, user_id))
        await db.commit()


async def get_operators():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM operators ORDER BY id") as c:
            return await c.fetchall()


async def get_operator(op_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM operators WHERE id=?", (op_id,)) as c:
            return await c.fetchone()


async def update_operator_price(op_id, field, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE operators SET {field}=? WHERE id=?", (value, op_id))
        await db.commit()


async def update_operator_name(op_id, name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE operators SET name=? WHERE id=?", (name, op_id))
        await db.commit()


async def toggle_operator(op_id, field):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE operators SET {field} = 1 - {field} WHERE id=?", (op_id,))
        await db.commit()


async def stop_all_operators():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE operators SET number_active=0, qr_active=0")
        await db.commit()


async def start_all_operators():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE operators SET number_active=1, qr_active=1")
        await db.commit()


# --- БАНЫ ---
async def ban_user(user_id, reason="Нарушение правил"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO banned_users (user_id, reason) VALUES (?, ?)", (user_id, reason))
        await db.commit()


async def unban_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM banned_users WHERE user_id=?", (user_id,))
        await db.commit()


async def is_user_banned(user_id) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM banned_users WHERE user_id=?", (user_id,)) as c:
            return (await c.fetchone()) is not None


# --- ЛОГИ ---
async def add_admin_log(admin_id, action, target):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO admin_logs (admin_id, action, target) VALUES (?, ?, ?)",
                         (admin_id, action, target))
        await db.commit()


async def get_admin_logs(limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT ?", (limit,)) as c:
            return await c.fetchall()


# --- ПОДПИСКИ НА ОПЕРАТОРОВ ---
async def sub_to_operator(user_id, op_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO operator_subs (user_id, operator_id) VALUES (?, ?)", (user_id, op_id))
        await db.commit()


async def get_operator_subs(op_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM operator_subs WHERE operator_id=?", (op_id,)) as c:
            return [r[0] for r in await c.fetchall()]


async def clear_operator_subs(op_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM operator_subs WHERE operator_id=?", (op_id,))
        await db.commit()


# --- ЭКСПОРТ В CSV ---
async def get_all_apps_export():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT a.id, a.user_id, u.username, a.mode, COALESCE(a.phone_number, a.qr_number) as val, 
                   o.name, a.status, a.created_at, a.processed_at
            FROM applications a 
            JOIN operators o ON o.id = a.operator_id
            LEFT JOIN users u ON u.user_id = a.user_id
            ORDER BY a.id DESC
        """) as c:
            return await c.fetchall()


async def get_all_withdrawals_export():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT w.id, w.user_id, u.username, w.amount, w.status, w.created_at
            FROM withdrawals w
            LEFT JOIN users u ON u.user_id = w.user_id
            ORDER BY w.id DESC
        """) as c:
            return await c.fetchall()


# --- АНТИ-СПАМ ---
async def check_active_app(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
                "SELECT COUNT(*) FROM applications WHERE user_id=? AND status IN ('pending', 'code_requested', 'code_sent')",
                (user_id,)) as c:
            return (await c.fetchone())[0] > 0


async def check_number_already_accepted(mode, number):
    async with aiosqlite.connect(DB_PATH) as db:
        if mode == "number":
            query = "SELECT COUNT(*) FROM applications WHERE mode='number' AND phone_number=? AND status='accepted'"
        else:
            query = "SELECT COUNT(*) FROM applications WHERE mode='qr' AND qr_number=? AND status='accepted'"
        async with db.execute(query, (number,)) as c:
            return (await c.fetchone())[0] > 0


# --- ЗАЯВКИ ---
async def create_application(**kw):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO applications (user_id, operator_id, mode, phone_number, qr_photo_id, qr_number)
            VALUES (?,?,?,?,?,?)
        """, (kw['user_id'], kw['operator_id'], kw['mode'], kw.get('phone_number'), kw.get('qr_photo_id'),
              kw.get('qr_number')))
        await db.commit()
        return cur.lastrowid


async def set_admin_message(app_id, chat_id, msg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE applications SET admin_chat_id=?, admin_message_id=? WHERE id=?",
                         (chat_id, msg_id, app_id))
        await db.commit()


async def get_application(app_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM applications WHERE id=?", (app_id,)) as c:
            return await c.fetchone()


async def update_app(app_id, **fields):
    if not fields: return
    keys = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [app_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE applications SET {keys} WHERE id=?", vals)
        await db.commit()


async def get_app_awaiting_code(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
                "SELECT * FROM applications WHERE user_id=? AND awaiting_code=1 AND status='code_requested' ORDER BY id DESC LIMIT 1",
                (user_id,)) as c:
            return await c.fetchone()


async def pending_payouts():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
                "SELECT * FROM applications WHERE status='accepted' AND payout_at IS NOT NULL AND payout_at <= datetime('now')") as c:
            return await c.fetchall()


async def get_all_pending_payouts():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM applications WHERE status='accepted' AND payout_at IS NOT NULL") as c:
            return await c.fetchall()


async def try_payout(app_id) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE applications SET payout_at=NULL WHERE id=? AND status='accepted' AND payout_at IS NOT NULL",
            (app_id,))
        await db.commit()
        return cur.rowcount == 1


# --- ИСТОРИЯ ---
async def get_user_applications(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM applications WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,)) as c:
            return await c.fetchall()


async def get_user_withdrawals(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,)) as c:
            return await c.fetchall()


async def get_total_withdrawn(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE user_id=? AND status='completed'",
                              (user_id,)) as c:
            return (await c.fetchone())[0]


# --- ТИКЕТЫ ---
async def create_ticket(user_id, message):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO tickets (user_id, message) VALUES (?, ?)", (user_id, message))
        await db.commit()
        return cur.lastrowid


async def get_user_tickets(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM tickets WHERE user_id=? ORDER BY id DESC", (user_id,)) as c:
            return await c.fetchall()


async def get_ticket(ticket_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)) as c:
            return await c.fetchone()


async def reply_ticket(ticket_id, reply_text):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tickets SET reply=? WHERE id=?", (reply_text, ticket_id))
        await db.commit()


async def close_ticket(ticket_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tickets SET status='closed' WHERE id=?", (ticket_id,))
        await db.commit()


# --- ВЫВОДЫ ---
async def create_withdrawal(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO withdrawals (user_id, amount) VALUES (?, ?)", (user_id, amount))
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))
        await db.commit()


async def get_pending_withdrawals():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE status='pending'") as c:
            return await c.fetchall()


async def approve_withdrawal(w_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE withdrawals SET status='completed' WHERE id=?", (w_id,))
        await db.commit()


# --- СТАТИСТИКА ---
async def stats_today():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COALESCE(SUM(CASE WHEN a.status='accepted' THEN 1 ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN a.status='rejected' THEN 1 ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN a.status='accepted' THEN CASE WHEN a.mode='number' THEN o.price_number ELSE o.price_qr END ELSE 0 END), 0)
            FROM applications a JOIN operators o ON o.id = a.operator_id WHERE date(a.processed_at) = date('now')
        """) as c:
            return await c.fetchone()


async def stats_total():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c: users = (await c.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(balance),0) FROM users") as c: balance = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM applications") as c: apps = (await c.fetchone())[0]
        return users, balance, apps


async def all_user_ids():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as c:
            return [r[0] for r in await c.fetchall()]


async def pending_amount(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COALESCE(SUM(CASE WHEN a.mode='number' THEN o.price_number ELSE o.price_qr END), 0)
            FROM applications a JOIN operators o ON o.id = a.operator_id
            WHERE a.user_id = ? AND (a.status IN ('pending', 'code_requested', 'code_sent') OR (a.status='accepted' AND a.payout_at IS NOT NULL AND a.payout_at > datetime('now')))
        """, (user_id,)) as c:
            return (await c.fetchone())[0]