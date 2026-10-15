"""SQLite storage for users and test sessions (answers are saved after every question)."""

import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    lang TEXT,
    sex TEXT,
    age INTEGER,
    created REAL
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    test_id TEXT NOT NULL,
    form TEXT NOT NULL,
    sex TEXT,
    age INTEGER,
    answers TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'setup',   -- setup | active | done | discarded
    result TEXT,
    created REAL,
    finished REAL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id, status);
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    test_id TEXT NOT NULL,
    form TEXT NOT NULL,
    stars INTEGER NOT NULL,
    charge_id TEXT UNIQUE NOT NULL,          -- telegram_payment_charge_id, needed for refunds
    created REAL,
    refunded REAL
);
CREATE INDEX IF NOT EXISTS purchases_user ON purchases(user_id, test_id, form);
"""


class Storage:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # --- users -------------------------------------------------------------
    def user(self, user_id):
        row = self.db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else {"user_id": user_id, "lang": None, "sex": None, "age": None}

    def set_user(self, user_id, **fields):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO users (user_id, created) VALUES (?, ?)", (user_id, time.time()))
            cols = ", ".join(f"{k} = ?" for k in fields)
            self.db.execute(f"UPDATE users SET {cols} WHERE user_id = ?", (*fields.values(), user_id))

    # --- sessions ----------------------------------------------------------
    def _session(self, row):
        if not row:
            return None
        s = dict(row)
        s["answers"] = {int(k): v for k, v in json.loads(s["answers"]).items()}
        s["result"] = json.loads(s["result"]) if s["result"] else None
        return s

    def open_session(self, user_id):
        """The user's test in progress (being set up or being answered), if any."""
        row = self.db.execute(
            "SELECT * FROM sessions WHERE user_id = ? AND status IN ('setup', 'active') ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return self._session(row)

    def latest_results(self, user_id):
        """The most recent finished session for each test the user has taken."""
        rows = self.db.execute(
            "SELECT * FROM sessions WHERE id IN (SELECT MAX(id) FROM sessions WHERE user_id = ? AND status = 'done' "
            "GROUP BY test_id) ORDER BY finished DESC",
            (user_id,),
        ).fetchall()
        return [self._session(r) for r in rows]

    def new_session(self, user_id, test_id, form):
        with self.db:
            self.db.execute(
                "UPDATE sessions SET status = 'discarded' WHERE user_id = ? AND status IN ('setup', 'active')",
                (user_id,),
            )
            cur = self.db.execute(
                "INSERT INTO sessions (user_id, test_id, form, created) VALUES (?, ?, ?, ?)",
                (user_id, test_id, form, time.time()),
            )
        return cur.lastrowid

    def update(self, session_id, **fields):
        if "answers" in fields:
            fields["answers"] = json.dumps(fields["answers"])
        if "result" in fields:
            fields["result"] = json.dumps(fields["result"])
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.db:
            self.db.execute(f"UPDATE sessions SET {cols} WHERE id = ?", (*fields.values(), session_id))

    def get(self, session_id):
        return self._session(self.db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())

    # --- purchases (Telegram Stars) ----------------------------------------
    def has_purchase(self, user_id, test_id, form):
        return self.db.execute(
            "SELECT 1 FROM purchases WHERE user_id = ? AND test_id = ? AND form = ? AND refunded IS NULL",
            (user_id, test_id, form),
        ).fetchone() is not None

    def add_purchase(self, user_id, test_id, form, stars, charge_id):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO purchases (user_id, test_id, form, stars, charge_id, created) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, test_id, form, stars, charge_id, time.time()),
            )

    def purchase(self, charge_id):
        row = self.db.execute("SELECT * FROM purchases WHERE charge_id = ?", (charge_id,)).fetchone()
        return dict(row) if row else None

    def mark_refunded(self, charge_id):
        with self.db:
            self.db.execute("UPDATE purchases SET refunded = ? WHERE charge_id = ?", (time.time(), charge_id))
