"""SQLite per-channel sliding-window message history."""
from __future__ import annotations

import time

import aiosqlite


class ChannelMemory:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id  TEXT NOT NULL,
                    user_id     TEXT,
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    ts          INTEGER NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_channel_ts ON channel_history(channel_id, ts)"
            )
            await db.commit()

    async def append(
        self, channel_id: str, role: str, content: str, user_id: str | None = None
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO channel_history (channel_id, user_id, role, content, ts) VALUES (?, ?, ?, ?, ?)",
                (channel_id, user_id, role, content, int(time.time())),
            )
            await db.commit()

    async def recent(self, channel_id: str, n: int = 10) -> list[dict]:
        """Return the last n messages in chronological order as {role, content}."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT role, content FROM channel_history WHERE channel_id=? ORDER BY id DESC LIMIT ?",
                (channel_id, n),
            ) as cur:
                rows = await cur.fetchall()
        rows.reverse()
        return [{"role": r, "content": c} for r, c in rows]
