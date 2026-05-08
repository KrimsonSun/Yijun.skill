"""Yijun Discord bot — entrypoint.

Pipeline per message:
1. mode_gate evaluates the latest user text → friend or intimate (with TTL)
2. memory.recent fetches the last 10 turns
3. prompt_builder assembles system + RAG few-shots + history + new user
4. asyncio.Queue serializes inference (CPU can only run one at a time)
5. llama-server returns text; safety_filter scrubs intimate words in friend mode
6. Reply sent; both turns persisted to memory

Env vars:
    DISCORD_TOKEN          required
    LLAMA_BASE_URL         default http://localhost:8080
    DB_PATH                default /var/lib/yijunbot/memory.db
    INDEX_DIR              default bot/.index
    ALERT_WEBHOOK_URL      optional — Discord webhook to ping Yijun when intimate mode activates
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from pathlib import Path

import discord
import httpx
from dotenv import load_dotenv

from .llm_client import LlamaClient
from .memory import ChannelMemory
from .mode_gate import ModeGate
from .prompt_builder import build_messages
from .retrieval import Retrieval
from .safety_filter import post_process

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("yijunbot")

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
LLAMA_BASE_URL = os.getenv("LLAMA_BASE_URL", "http://localhost:8080")
DB_PATH = os.getenv("DB_PATH", "/var/lib/yijunbot/memory.db")
INDEX_DIR = os.getenv("INDEX_DIR", "bot/.index")
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL")

RATE_LIMIT_SEC = 5
HISTORY_TURNS = 10
MAX_TOKENS = 256


async def send_alert(msg: str) -> None:
    if not ALERT_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(ALERT_WEBHOOK_URL, json={"content": msg})
    except Exception:  # noqa: BLE001
        logger.exception("alert webhook failed")


class YijunBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.dm_messages = True
        super().__init__(intents=intents)

        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

        self.gate = ModeGate(DB_PATH)
        self.memory = ChannelMemory(DB_PATH)
        self.llm = LlamaClient(base_url=LLAMA_BASE_URL)
        self.retrieval = Retrieval(index_dir=Path(INDEX_DIR))
        self.queue: asyncio.Queue = asyncio.Queue()
        self.last_msg_ts: dict[str, float] = defaultdict(float)
        self._worker_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        await self.gate.init()
        await self.memory.init()
        # Loading the FAISS index is sync but quick (<1s for 23k vectors)
        try:
            self.retrieval.load()
        except FileNotFoundError:
            logger.error(
                "Retrieval index not found at %s — run `python -m bot.retrieval` first",
                INDEX_DIR,
            )
            raise
        self._worker_task = asyncio.create_task(self._worker())

    async def on_ready(self) -> None:  # type: ignore[override]
        logger.info("logged in as %s (id=%s)", self.user, getattr(self.user, "id", "?"))

    async def on_message(self, message: discord.Message) -> None:  # type: ignore[override]
        if message.author.bot or message.author == self.user:
            return
        # Only respond to DMs or messages that mention the bot
        is_dm = message.guild is None
        is_mention = self.user is not None and self.user in message.mentions
        if not (is_dm or is_mention):
            return

        user_id = str(message.author.id)
        channel_id = str(message.channel.id)

        # Rate limit per user
        now = time.time()
        if now - self.last_msg_ts[user_id] < RATE_LIMIT_SEC:
            return
        self.last_msg_ts[user_id] = now

        # Strip the bot mention so the model doesn't see "@bot"
        text = message.content
        if self.user is not None:
            text = text.replace(f"<@{self.user.id}>", "").replace(
                f"<@!{self.user.id}>", ""
            ).strip()
        if not text:
            return

        await self.queue.put((message, user_id, channel_id, text))

    async def _worker(self) -> None:
        """Single-concurrency inference worker."""
        while True:
            message, user_id, channel_id, text = await self.queue.get()
            try:
                await self._handle_one(message, user_id, channel_id, text)
            except Exception:  # noqa: BLE001
                logger.exception("inference handler failed")
            finally:
                self.queue.task_done()

    async def _handle_one(
        self,
        message: discord.Message,
        user_id: str,
        channel_id: str,
        text: str,
    ) -> None:
        decision = await self.gate.evaluate(user_id, channel_id, text)
        mode = decision.mode

        if decision.just_activated:
            await send_alert(
                f"🚨 intimate mode activated: user_id={user_id} channel={channel_id} "
                f"text={text[:120]!r}"
            )

        history = await self.memory.recent(channel_id, n=HISTORY_TURNS)
        messages = build_messages(
            mode=mode,
            user_message=text,
            history=history,
            retrieval=self.retrieval,
        )

        async with message.channel.typing():
            try:
                raw = await self.llm.chat(messages, max_tokens=MAX_TOKENS)
            except Exception:  # noqa: BLE001
                logger.exception("llama-server call failed")
                await message.reply("（卡住了，等会儿再说）", mention_author=False)
                return

        reply = post_process(raw, mode)
        if not reply:
            reply = "嘿嘿"

        await message.reply(reply, mention_author=False)

        # Persist both turns. We store the raw user text and the post-processed reply.
        await self.memory.append(channel_id, "user", text, user_id=user_id)
        await self.memory.append(channel_id, "assistant", reply)


def main() -> None:
    bot = YijunBot()
    bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
