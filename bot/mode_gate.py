"""Dual-mode context gate.

friend (default) -> bot must NOT use intimate vocab (宝宝/mua/猪猪/etc.)
intimate          -> activated when a message simultaneously contains 鱼鱼 AND
                     a partner-identity claim (我是你对象 / 女朋友 / 男朋友 / 宝宝)

State is stored per (user_id, channel_id) with a 24h TTL. Users can manually
revert with `/lock` or by saying 切回普通.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Literal

import aiosqlite

logger = logging.getLogger(__name__)

Mode = Literal["friend", "intimate"]
DEFAULT_MODE: Mode = "friend"
INTIMATE_TTL_SEC = 24 * 60 * 60

# Trigger requires BOTH the partner's name and an identity claim — guards
# against "鱼鱼" appearing in unrelated contexts (e.g. literally fish).
NAME_PATTERN = re.compile(r"鱼鱼")
IDENTITY_PATTERN = re.compile(
    r"(我是你?|我就是你?)?\s*(对象|女朋友|男朋友|宝宝|老婆|老公|媳妇)"
)
LOCK_PATTERN = re.compile(r"(/lock|切回普通|切回正常|关闭亲密)")


@dataclass
class GateDecision:
    mode: Mode
    just_activated: bool  # True only on the message that flipped to intimate
    just_locked: bool     # True only on the message that flipped back to friend


class ModeGate:
    """SQLite-backed per-(user, channel) mode store + activation logic."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_mode (
                    user_id     TEXT NOT NULL,
                    channel_id  TEXT NOT NULL,
                    mode        TEXT NOT NULL,
                    expires_at  INTEGER,
                    activated_at INTEGER,
                    PRIMARY KEY (user_id, channel_id)
                )
                """
            )
            await db.commit()

    async def get_mode(self, user_id: str, channel_id: str) -> Mode:
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT mode, expires_at FROM user_mode WHERE user_id=? AND channel_id=?",
                (user_id, channel_id),
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return DEFAULT_MODE
        mode, expires_at = row
        if mode == "intimate" and expires_at is not None and expires_at < now:
            await self._set(user_id, channel_id, DEFAULT_MODE, None)
            return DEFAULT_MODE
        return mode  # type: ignore[return-value]

    async def _set(
        self, user_id: str, channel_id: str, mode: Mode, expires_at: int | None
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_mode (user_id, channel_id, mode, expires_at, activated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, channel_id) DO UPDATE SET
                    mode=excluded.mode,
                    expires_at=excluded.expires_at,
                    activated_at=excluded.activated_at
                """,
                (user_id, channel_id, mode, expires_at, int(time.time())),
            )
            await db.commit()

    async def evaluate(
        self, user_id: str, channel_id: str, text: str
    ) -> GateDecision:
        """Inspect the latest user message; flip mode if triggered."""
        current = await self.get_mode(user_id, channel_id)

        if LOCK_PATTERN.search(text) and current == "intimate":
            await self._set(user_id, channel_id, DEFAULT_MODE, None)
            logger.info("mode_gate: locked %s @ %s", user_id, channel_id)
            return GateDecision(mode=DEFAULT_MODE, just_activated=False, just_locked=True)

        if (
            current != "intimate"
            and NAME_PATTERN.search(text)
            and IDENTITY_PATTERN.search(text)
        ):
            expires = int(time.time()) + INTIMATE_TTL_SEC
            await self._set(user_id, channel_id, "intimate", expires)
            logger.warning(
                "mode_gate: ACTIVATED intimate for %s @ %s (text=%r)",
                user_id,
                channel_id,
                text[:80],
            )
            return GateDecision(mode="intimate", just_activated=True, just_locked=False)

        return GateDecision(mode=current, just_activated=False, just_locked=False)
