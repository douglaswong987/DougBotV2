import aiosqlite
from datetime import datetime
import pytz

TZ = pytz.timezone("US/Pacific")

def today_pst() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


import os
DB_PATH = os.path.join(os.getenv('DATA_DIR', '.'), 'dougbot.db')


class Database:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    @classmethod
    async def create(cls):
        conn = await aiosqlite.connect(DB_PATH)
        conn.row_factory = aiosqlite.Row
        db = cls(conn)
        await db._init_schema()
        return db

    async def _init_schema(self):
        await self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS cock_lengths (
                user_id     TEXT NOT NULL,
                guild_id    TEXT NOT NULL,
                length      REAL NOT NULL,
                date        TEXT NOT NULL,
                PRIMARY KEY (user_id, guild_id, date)
            );

            CREATE TABLE IF NOT EXISTS insults (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                message     TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS insult_specials (
                guild_id    TEXT NOT NULL,
                user_id     TEXT NOT NULL,
                message     TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                guild_id    TEXT NOT NULL,
                event_name  TEXT NOT NULL,
                fire_at     TEXT NOT NULL,
                fired       INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id    TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                PRIMARY KEY (guild_id, key)
            );

            CREATE TABLE IF NOT EXISTS insult_targets (
                guild_id    TEXT NOT NULL,
                user_id     TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS insult_roles (
                guild_id    TEXT NOT NULL,
                role_id     TEXT NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            );
        ''')
        await self.conn.commit()

    # -------------------------------------------------------------------------
    # Cock lengths
    # -------------------------------------------------------------------------

    async def get_cock_length(self, user_id: int, guild_id: int) -> float | None:
        today = today_pst()
        async with self.conn.execute(
            'SELECT length FROM cock_lengths WHERE user_id=? AND guild_id=? AND date=?',
            (str(user_id), str(guild_id), today)
        ) as cur:
            row = await cur.fetchone()
            return row['length'] if row else None

    async def set_cock_length(self, user_id: int, guild_id: int, length: float):
        today = today_pst()
        await self.conn.execute(
            '''INSERT INTO cock_lengths (user_id, guild_id, length, date)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, guild_id, date) DO UPDATE SET length=excluded.length''',
            (str(user_id), str(guild_id), length, today)
        )
        await self.conn.commit()

    async def get_cock_leaderboard(self, guild_id: int):
        today = today_pst()
        async with self.conn.execute(
            '''SELECT user_id, length FROM cock_lengths
               WHERE guild_id=? AND date=?
               ORDER BY length DESC''',
            (str(guild_id), today)
        ) as cur:
            return await cur.fetchall()

    # -------------------------------------------------------------------------
    # Reminders
    # -------------------------------------------------------------------------

    async def add_reminder(self, reminder_id: str, user_id: int, guild_id: int,
                           event_name: str, fire_at: str):
        await self.conn.execute(
            '''INSERT INTO reminders (id, user_id, guild_id, event_name, fire_at)
               VALUES (?, ?, ?, ?, ?)''',
            (reminder_id, str(user_id), str(guild_id), event_name, fire_at)
        )
        await self.conn.commit()

    async def get_pending_reminders(self):
        async with self.conn.execute(
            "SELECT * FROM reminders WHERE fired=0"
        ) as cur:
            return await cur.fetchall()

    async def get_user_reminders(self, user_id: int):
        async with self.conn.execute(
            "SELECT * FROM reminders WHERE user_id=? AND fired=0 ORDER BY fire_at",
            (str(user_id),)
        ) as cur:
            return await cur.fetchall()

    async def mark_reminder_fired(self, reminder_id: str):
        await self.conn.execute(
            "UPDATE reminders SET fired=1 WHERE id=?",
            (reminder_id,)
        )
        await self.conn.commit()

    async def delete_reminder(self, reminder_id: str, user_id: int) -> bool:
        async with self.conn.execute(
            "SELECT id FROM reminders WHERE id=? AND user_id=? AND fired=0",
            (reminder_id, str(user_id))
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        await self.conn.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
        await self.conn.commit()
        return True

    async def delete_all_user_reminders(self, user_id: int) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) as cnt FROM reminders WHERE user_id=? AND fired=0",
            (str(user_id),)
        ) as cur:
            row = await cur.fetchone()
            count = row['cnt']
        await self.conn.execute(
            "DELETE FROM reminders WHERE user_id=? AND fired=0",
            (str(user_id),)
        )
        await self.conn.commit()
        return count

    # -------------------------------------------------------------------------
    # Guild config
    # -------------------------------------------------------------------------

    async def get_config(self, guild_id: int, key: str) -> str | None:
        async with self.conn.execute(
            'SELECT value FROM guild_config WHERE guild_id=? AND key=?',
            (str(guild_id), key)
        ) as cur:
            row = await cur.fetchone()
            return row['value'] if row else None

    async def set_config(self, guild_id: int, key: str, value: str):
        await self.conn.execute(
            '''INSERT INTO guild_config (guild_id, key, value)
               VALUES (?, ?, ?)
               ON CONFLICT(guild_id, key) DO UPDATE SET value=excluded.value''',
            (str(guild_id), key, value)
        )
        await self.conn.commit()

    async def delete_config(self, guild_id: int, key: str):
        await self.conn.execute(
            'DELETE FROM guild_config WHERE guild_id=? AND key=?',
            (str(guild_id), key)
        )
        await self.conn.commit()

    # -------------------------------------------------------------------------
    # Insult targets
    # -------------------------------------------------------------------------

    async def add_insult_target(self, guild_id: int, user_id: int):
        await self.conn.execute(
            '''INSERT OR IGNORE INTO insult_targets (guild_id, user_id)
               VALUES (?, ?)''',
            (str(guild_id), str(user_id))
        )
        await self.conn.commit()

    async def remove_insult_target(self, guild_id: int, user_id: int):
        await self.conn.execute(
            'DELETE FROM insult_targets WHERE guild_id=? AND user_id=?',
            (str(guild_id), str(user_id))
        )
        await self.conn.commit()

    async def get_insult_targets(self, guild_id: int):
        async with self.conn.execute(
            'SELECT user_id FROM insult_targets WHERE guild_id=?',
            (str(guild_id),)
        ) as cur:
            rows = await cur.fetchall()
            return [int(r['user_id']) for r in rows]

    async def add_insult_role(self, guild_id: int, role_id: int):
        await self.conn.execute(
            '''INSERT OR IGNORE INTO insult_roles (guild_id, role_id)
               VALUES (?, ?)''',
            (str(guild_id), str(role_id))
        )
        await self.conn.commit()

    async def remove_insult_role(self, guild_id: int, role_id: int):
        await self.conn.execute(
            'DELETE FROM insult_roles WHERE guild_id=? AND role_id=?',
            (str(guild_id), str(role_id))
        )
        await self.conn.commit()

    async def get_insult_roles(self, guild_id: int):
        async with self.conn.execute(
            'SELECT role_id FROM insult_roles WHERE guild_id=?',
            (str(guild_id),)
        ) as cur:
            rows = await cur.fetchall()
            return [int(r['role_id']) for r in rows]

    # -------------------------------------------------------------------------
    # Insult specials
    # -------------------------------------------------------------------------

    async def set_insult_special(self, guild_id: int, user_id: int, message: str):
        await self.conn.execute(
            '''INSERT INTO insult_specials (guild_id, user_id, message)
               VALUES (?, ?, ?)
               ON CONFLICT(guild_id, user_id) DO UPDATE SET message=excluded.message''',
            (str(guild_id), str(user_id), message)
        )
        await self.conn.commit()

    async def clear_insult_special(self, guild_id: int, user_id: int):
        await self.conn.execute(
            'DELETE FROM insult_specials WHERE guild_id=? AND user_id=?',
            (str(guild_id), str(user_id))
        )
        await self.conn.commit()

    async def get_insult_special(self, guild_id: int, user_id: int) -> str | None:
        async with self.conn.execute(
            'SELECT message FROM insult_specials WHERE guild_id=? AND user_id=?',
            (str(guild_id), str(user_id))
        ) as cur:
            row = await cur.fetchone()
            return row['message'] if row else None

    async def get_all_insult_specials(self, guild_id: int):
        async with self.conn.execute(
            'SELECT user_id, message FROM insult_specials WHERE guild_id=?',
            (str(guild_id),)
        ) as cur:
            return await cur.fetchall()

    # -------------------------------------------------------------------------
    # Global insult dictionary
    # -------------------------------------------------------------------------

    async def add_insult(self, message: str) -> bool:
        """Returns False if the insult already exists."""
        try:
            await self.conn.execute(
                'INSERT INTO insults (message) VALUES (?)', (message,)
            )
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove_insult(self, insult_id: int) -> bool:
        """Returns False if the ID doesn't exist."""
        async with self.conn.execute(
            'SELECT id FROM insults WHERE id=?', (insult_id,)
        ) as cur:
            if not await cur.fetchone():
                return False
        await self.conn.execute('DELETE FROM insults WHERE id=?', (insult_id,))
        await self.conn.commit()
        return True

    async def get_insults(self) -> list:
        async with self.conn.execute(
            'SELECT id, message FROM insults ORDER BY id'
        ) as cur:
            return await cur.fetchall()

    async def get_insult_count(self) -> int:
        async with self.conn.execute('SELECT COUNT(*) as cnt FROM insults') as cur:
            row = await cur.fetchone()
            return row['cnt']
