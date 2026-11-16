import aiosqlite

DB_PATH = "bot.db"

STATUS_RU = {
    "pending": "На проверке", "accepted": "Принята", "rejected": "Отклонена",
    "cancelled": "Отменена", "code_requested": "Запрошен код", "code_sent": "Код отправлен",
}
MODE_RU = {"number": "Номер", "qr": "QR"}


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
            id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, target TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS operator_subs (
            user_id INTEGER, operator_id INTEGER, PRIMARY KEY(user_id, operator_id)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        );
        """)
        await _run_migrations(db)
        for k, v in {
            "auto_work": "1", "min_withdraw": "5.0",
            "work_start": "06:00", "work_end": "19:00",
            "urgent_support_link": "", "maintenance": "0",
            "auto_payout": "1", "qr_cooldown": "40",
            "ref_bonus": "0.5", "rejection_cooldown": "15",
        }.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

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
                    "INSERT INTO operators (name, emoji_id, price_number, price_qr, "
                    "supports_number, supports_qr, number_active, qr_active, category) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, eid, p_num, p_qr, s_num, s_qr, n_act, q_act, cat))
        await db.commit()


async def _run_migrations(db):
    cur = await db.execute("PRAGMA table_info(withdrawals)")
    cols = {row[1] for row in await cur.fetchall()}
    if "check_link" not in cols:
        await db.execute("ALTER TABLE withdrawals ADD COLUMN check_link TEXT")
    if "completed_at" not in cols:
        await db.execute("ALTER TABLE withdrawals ADD COLUMN completed_at TIMESTAMP")
    if "reject_reason" not in cols:
        await db.execute("ALTER TABLE withdrawals ADD COLUMN reject_reason TEXT")
    await db.commit()


# SETTINGS
async def get_setting(key):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key=?", (key,)) as c:
            row = await c.fetchone()
            return row[0] if row else None


async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()


async def get_setting_float(key, default=0.0):
    v = await get_setting(key)
    try: return float(v) if v is not None else default
    except (TypeError, ValueError): return default


async def get_setting_int(key, default=0):
    v = await get_setting(key)
    try: return int(v) if v is not None else default
    except (TypeError, ValueError): return default


async def get_setting_bool(key, default=False):
    v = await get_setting(key)
    if v is None: return default
    return str(v) in ("1", "true", "True", "yes")


async def get_min_withdraw():       return await get_setting_float("min_withdraw", 5.0)
async def get_work_start():         return await get_setting("work_start") or "06:00"
async def get_work_end():           return await get_setting("work_end") or "19:00"
async def get_urgent_support_link(): return (await get_setting("urgent_support_link") or "").strip()
async def is_maintenance():         return await get_setting_bool("maintenance")
async def is_auto_payout():         return await get_setting_bool("auto_payout", True)


# USERS
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
        await db.execute("UPDATE users SET balance = MAX(0, balance + ?) WHERE user_id=?", (amount, user_id))
        await db.commit()


async def increment_orders(user_id, success: bool, amount: int = 1):
    field = "successful_orders" if success else "failed_orders"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {field} = MAX(0, {field} + ?) WHERE user_id=?", (amount, user_id))
        await db.commit()


# OPERATORS
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


# BANS / LOGS
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


# OPERATOR SUBS
async def sub_to_operator(user_id, op_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO operator_subs (user_id, operator_id) VALUES (?, ?)",
                         (user_id, op_id))
        await db.commit()


async def get_operator_subs(op_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM operator_subs WHERE operator_id=?", (op_id,)) as c:
            return [r[0] for r in await c.fetchall()]


async def clear_operator_subs(op_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM operator_subs WHERE operator_id=?", (op_id,))
        await db.commit()


# APPLICATIONS
async def check_number_already_accepted(mode, number):
    async with aiosqlite.connect(DB_PATH) as db:
        active = "('pending','code_requested','code_sent','accepted')"
        if mode == "number":
            q = f"SELECT COUNT(*) FROM applications WHERE mode='number' AND phone_number=? AND status IN {active}"
        else:
            q = f"SELECT COUNT(*) FROM applications WHERE mode='qr' AND qr_number=? AND status IN {active}"
        async with db.execute(q, (number,)) as c:
            return (await c.fetchone())[0] > 0


async def get_last_rejection_time(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT processed_at FROM applications
            WHERE user_id=? AND status='rejected' AND processed_at IS NOT NULL
            ORDER BY processed_at DESC LIMIT 1
        """, (user_id,)) as c:
            row = await c.fetchone()
            return row[0] if row else None


async def create_application(**kw):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO applications (user_id, operator_id, mode, phone_number, qr_photo_id, qr_number)
            VALUES (?,?,?,?,?,?)
        """, (kw['user_id'], kw['operator_id'], kw['mode'], kw.get('phone_number'),
              kw.get('qr_photo_id'), kw.get('qr_number')))
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
                "SELECT * FROM applications WHERE user_id=? AND awaiting_code=1 AND status='code_requested' "
                "ORDER BY id DESC LIMIT 1", (user_id,)) as c:
            return await c.fetchone()


async def pending_payouts():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
                "SELECT * FROM applications WHERE status='accepted' AND payout_at IS NOT NULL "
                "AND payout_at <= datetime('now')") as c:
            return await c.fetchall()


async def get_all_pending_payouts():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
                "SELECT * FROM applications WHERE status='accepted' AND payout_at IS NOT NULL") as c:
            return await c.fetchall()


async def try_payout(app_id) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE applications SET payout_at=NULL WHERE id=? AND status='accepted' AND payout_at IS NOT NULL",
            (app_id,))
        await db.commit()
        return cur.rowcount == 1


async def get_user_applications(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM applications WHERE user_id=? ORDER BY id DESC LIMIT 10",
                              (user_id,)) as c:
            return await c.fetchall()


async def get_all_active_apps():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT a.*, u.username, u.full_name, o.name AS op_name
            FROM applications a
            LEFT JOIN users u ON u.user_id = a.user_id
            LEFT JOIN operators o ON o.id = a.operator_id
            WHERE a.status IN ('pending','code_requested','code_sent')
            ORDER BY a.id DESC
        """) as c:
            return await c.fetchall()


# WITHDRAWALS
async def get_user_withdrawals(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC LIMIT 20",
                              (user_id,)) as c:
            return await c.fetchall()


async def get_withdrawal(w_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE id=?", (w_id,)) as c:
            return await c.fetchone()


async def get_total_withdrawn(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE user_id=? AND status='completed'",
                (user_id,)) as c:
            return (await c.fetchone())[0]


async def get_pending_withdrawn(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE user_id=? AND status='pending'",
                (user_id,)) as c:
            return (await c.fetchone())[0]


async def get_total_fines(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COALESCE(SUM(o.price_qr), 0)
            FROM applications a JOIN operators o ON o.id = a.operator_id
            WHERE a.user_id = ? AND a.mode='qr' AND a.status='rejected' AND a.reject_reason='block'
        """, (user_id,)) as c:
            return (await c.fetchone())[0]


async def create_withdrawal(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO withdrawals (user_id, amount) VALUES (?, ?)", (user_id, amount))
        await db.execute("UPDATE users SET balance = MAX(0, balance - ?) WHERE user_id=?", (amount, user_id))
        await db.commit()


async def get_pending_withdrawals():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE status='pending' ORDER BY id") as c:
            return await c.fetchall()


async def approve_withdrawal(w_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE withdrawals SET status='completed' WHERE id=?", (w_id,))
        await db.commit()


async def complete_withdrawal(w_id, check_link=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE withdrawals SET status='completed', check_link=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (check_link, w_id))
        await db.commit()


async def cancel_withdrawal(w_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE withdrawals SET status='cancelled', reject_reason='Отменено администратором', "
            "completed_at=CURRENT_TIMESTAMP WHERE id=?", (w_id,))
        await db.commit()


# USER INFO / STATS
async def get_user_info_stats(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as c:
            u = await c.fetchone()
        async with db.execute("SELECT COUNT(*) FROM applications WHERE user_id=?", (user_id,)) as c:
            total_apps = (await c.fetchone())[0]
        async with db.execute(
                "SELECT COUNT(*) FROM applications WHERE user_id=? AND status IN "
                "('pending','code_requested','code_sent')", (user_id,)) as c:
            pending = (await c.fetchone())[0]
        async with db.execute(
                "SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE user_id=? AND status='pending'",
                (user_id,)) as c:
            pending_wd = (await c.fetchone())[0]
        async with db.execute(
                "SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE user_id=? AND status='completed'",
                (user_id,)) as c:
            total_wd = (await c.fetchone())[0]
        return u, total_apps, pending, pending_wd, total_wd


async def daily_stats_for_admin():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status='accepted' AND date(processed_at)=date('now') THEN 1 ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN status='rejected' AND date(processed_at)=date('now') THEN 1 ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN status='rejected' AND reject_reason='block' AND date(processed_at)=date('now') THEN 1 ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN status='rejected' AND reject_reason='slet' AND date(processed_at)=date('now') THEN 1 ELSE 0 END), 0)
            FROM applications
        """) as c:
            row = await c.fetchone()
        async with db.execute(
                "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM withdrawals "
                "WHERE status='completed' AND date(completed_at)=date('now')") as c:
            wrow = await c.fetchone()
        return {"accepted": row[0] or 0, "rejected": row[1] or 0,
                "block": row[2] or 0, "slet": row[3] or 0,
                "paid_count": wrow[0] or 0, "paid_sum": wrow[1] or 0.0}


async def get_advanced_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.user_id, u.username, u.full_name,
                   COALESCE(SUM(CASE WHEN a.mode='number' THEN o.price_number ELSE o.price_qr END),0) AS earned,
                   COUNT(a.id) AS cnt
            FROM users u
            LEFT JOIN applications a ON a.user_id=u.user_id AND a.status='accepted'
            LEFT JOIN operators o ON o.id=a.operator_id
            GROUP BY u.user_id ORDER BY earned DESC LIMIT 5
        """) as c:
            top_users = await c.fetchall()
        async with db.execute("""
            SELECT o.name, COUNT(a.id) AS cnt,
                   COALESCE(SUM(CASE WHEN a.mode='number' THEN o.price_number ELSE o.price_qr END),0) AS total_sum
            FROM operators o LEFT JOIN applications a ON a.operator_id=o.id AND a.status='accepted'
            GROUP BY o.id ORDER BY cnt DESC LIMIT 5
        """) as c:
            top_ops = await c.fetchall()
        async with db.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status='accepted' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status IN ('pending','code_requested','code_sent') THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END),0),
                COUNT(*)
            FROM applications
        """) as c:
            row = await c.fetchone()
        async with db.execute("""
            SELECT date(processed_at) AS d, COUNT(*) AS cnt
            FROM applications WHERE status='accepted' AND processed_at >= date('now','-7 days')
            GROUP BY d ORDER BY d
        """) as c:
            week = await c.fetchall()
        return {"top_users": top_users, "top_ops": top_ops,
                "accepted": row[0], "pending": row[1], "rejected": row[2], "total": row[3],
                "week": week}


async def get_day_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE date(created_at)=date('now')") as c:
            new_users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*), COALESCE(SUM(balance),0) FROM users") as c:
            total_users, total_balance = await c.fetchone()
        async with db.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status='accepted' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='rejected' AND reject_reason='block' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='rejected' AND reject_reason='slet' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='rejected' AND (reject_reason IS NULL OR reject_reason NOT IN ('block','slet')) THEN 1 ELSE 0 END),0)
            FROM applications WHERE date(processed_at)=date('now')
        """) as c:
            acc, block, slet, other_rej = await c.fetchone()
        async with db.execute(
                "SELECT COUNT(*) FROM applications WHERE status IN ('pending','code_requested','code_sent')") as c:
            pending = (await c.fetchone())[0]
        async with db.execute("""
            SELECT COALESCE(SUM(CASE WHEN a.mode='number' THEN o.price_number ELSE o.price_qr END),0)
            FROM applications a JOIN operators o ON o.id=a.operator_id
            WHERE a.status='accepted' AND date(a.processed_at)=date('now')
        """) as c:
            acc_sum = (await c.fetchone())[0]
        async with db.execute("""
            SELECT COUNT(DISTINCT a.operator_id) FROM applications a
            WHERE a.status='accepted' AND date(a.processed_at)=date('now')
        """) as c:
            active_ops = (await c.fetchone())[0]
        async with db.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='completed' THEN amount ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='pending' THEN amount ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END),0)
            FROM withdrawals
            WHERE date(created_at)=date('now') OR date(completed_at)=date('now')
        """) as c:
            wd_c, wd_c_sum, wd_p, wd_p_sum, wd_x = await c.fetchone()
        return {
            "new_users": new_users, "total_users": total_users, "total_balance": total_balance,
            "accepted": acc, "block": block, "slet": slet, "other_rej": other_rej, "pending": pending,
            "acc_sum": acc_sum, "active_ops": active_ops,
            "wd_completed": wd_c, "wd_completed_sum": wd_c_sum,
            "wd_pending": wd_p, "wd_pending_sum": wd_p_sum, "wd_cancelled": wd_x,
        }


async def get_total_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*), COALESCE(SUM(balance),0) FROM users") as c:
            total_users, total_balance = await c.fetchone()
        async with db.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status='accepted' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='rejected' AND reject_reason='block' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='rejected' AND reject_reason='slet' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status IN ('pending','code_requested','code_sent') THEN 1 ELSE 0 END),0),
                COUNT(*)
            FROM applications
        """) as c:
            acc, block, slet, all_rej, pending, total_apps = await c.fetchone()
        async with db.execute("""
            SELECT COALESCE(SUM(CASE WHEN a.mode='number' THEN o.price_number ELSE o.price_qr END),0)
            FROM applications a JOIN operators o ON o.id=a.operator_id
            WHERE a.status='accepted'
        """) as c:
            acc_sum = (await c.fetchone())[0]
        async with db.execute("""
            SELECT COALESCE(SUM(o.price_qr),0)
            FROM applications a JOIN operators o ON o.id=a.operator_id
            WHERE a.status='rejected' AND a.reject_reason='block'
        """) as c:
            fines_sum = (await c.fetchone())[0]
        async with db.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='completed' THEN amount ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='pending' THEN amount ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END),0)
            FROM withdrawals
        """) as c:
            wd_c, wd_c_sum, wd_p, wd_p_sum, wd_x = await c.fetchone()
        async with db.execute("SELECT COUNT(DISTINCT operator_id) FROM applications WHERE status='accepted'") as c:
            active_ops = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM operators") as c:
            total_ops = (await c.fetchone())[0]
        return {
            "total_users": total_users, "total_balance": total_balance,
            "accepted": acc, "block": block, "slet": slet, "all_rej": all_rej,
            "pending": pending, "total_apps": total_apps,
            "acc_sum": acc_sum, "fines_sum": fines_sum,
            "active_ops": active_ops, "total_ops": total_ops,
            "wd_completed": wd_c, "wd_completed_sum": wd_c_sum,
            "wd_pending": wd_p, "wd_pending_sum": wd_p_sum, "wd_cancelled": wd_x,
        }


# USER FEATURES
async def get_referral_stats(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (user_id,)) as c:
            count = (await c.fetchone())[0]
        async with db.execute("""
            SELECT COUNT(DISTINCT u.user_id) FROM users u
            JOIN applications a ON a.user_id = u.user_id
            WHERE u.referrer_id=? AND a.status='accepted'
        """, (user_id,)) as c:
            active = (await c.fetchone())[0]
        return count, active


async def get_user_weekly_stats(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN a.status='accepted' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN a.status='rejected' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN a.status='accepted' THEN
                    CASE WHEN a.mode='number' THEN o.price_number ELSE o.price_qr END ELSE 0 END),0)
            FROM applications a JOIN operators o ON o.id=a.operator_id
            WHERE a.user_id=? AND a.created_at >= date('now','-7 days')
        """, (user_id,)) as c:
            return await c.fetchone()


async def get_user_rank(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COUNT(*) + 1 FROM users
            WHERE successful_orders > (SELECT successful_orders FROM users WHERE user_id=?)
        """, (user_id,)) as c:
            return (await c.fetchone())[0]


async def get_top_users(limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT user_id, username, full_name, successful_orders
            FROM users WHERE successful_orders > 0
            ORDER BY successful_orders DESC LIMIT ?
        """, (limit,)) as c:
            return await c.fetchall()


# TICKETS
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


# MISC
async def stats_today():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COALESCE(SUM(CASE WHEN a.status='accepted' THEN 1 ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN a.status='rejected' THEN 1 ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN a.status='accepted' THEN
                       CASE WHEN a.mode='number' THEN o.price_number ELSE o.price_qr END ELSE 0 END), 0)
            FROM applications a JOIN operators o ON o.id = a.operator_id
            WHERE date(a.processed_at) = date('now')
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
            WHERE a.user_id = ? AND (a.status IN ('pending','code_requested','code_sent')
                OR (a.status='accepted' AND a.payout_at IS NOT NULL AND a.payout_at > datetime('now')))
        """, (user_id,)) as c:
            return (await c.fetchone())[0]


# CSV EXPORT
async def get_full_apps_export():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT a.id, a.user_id, COALESCE(u.username,'—'), COALESCE(u.full_name,'—'),
                   a.mode, COALESCE(a.phone_number, a.qr_number, '—'),
                   o.name, o.price_number, o.price_qr,
                   a.status, COALESCE(a.reject_reason,''), a.created_at, a.processed_at, a.code
            FROM applications a
            JOIN operators o ON o.id = a.operator_id
            LEFT JOIN users u ON u.user_id = a.user_id
            ORDER BY a.id DESC
        """) as c:
            return await c.fetchall()


async def get_full_withdrawals_export():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT w.id, w.user_id, COALESCE(u.username,'—'), COALESCE(u.full_name,'—'),
                   w.amount, w.status, COALESCE(w.reject_reason,''), COALESCE(w.check_link,''),
                   w.created_at, w.completed_at
            FROM withdrawals w LEFT JOIN users u ON u.user_id = w.user_id
            ORDER BY w.id DESC
        """) as c:
            return await c.fetchall()


async def get_full_users_export():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT u.user_id, COALESCE(u.username,'—'), COALESCE(u.full_name,'—'),
                   u.balance, u.successful_orders, u.failed_orders,
                   COALESCE(u.referrer_id, 0), u.created_at
            FROM users u ORDER BY u.user_id
        """) as c:
            return await c.fetchall()


async def get_summary_export():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c: users = (await c.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(balance),0) FROM users") as c: bal = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM applications") as c: apps = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM applications WHERE status='accepted'") as c: acc = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM applications WHERE status='rejected'") as c: rej = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM withdrawals WHERE status='completed'") as c: wpaid = (await c.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='completed'") as c: wsum = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'") as c: wpend = (await c.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='pending'") as c: wpend_sum = (await c.fetchone())[0]
        return {"users": users, "balance": bal, "apps": apps, "accepted": acc, "rejected": rej,
                "wpaid": wpaid, "wsum": wsum, "wpend": wpend, "wpend_sum": wpend_sum}