"""Tiny in-process pub/sub for WebSocket fanout.

Apply phase creates this as backend/realtime.py. Both the chat tool dispatcher
(server-side) and the WS routes (client-facing) import from here.

Kept small on purpose — Yijun's stack is single-instance FastAPI in Docker.
If the deployment ever scales horizontally, swap the in-process dict for Redis
pub/sub without touching callers.
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_channels: dict[str, set[WebSocket]] = defaultdict(set)
_lock = asyncio.Lock()


async def register_channel(channel: str, ws: WebSocket) -> None:
    async with _lock:
        _channels[channel].add(ws)


async def unregister_channel(channel: str, ws: WebSocket) -> None:
    async with _lock:
        _channels[channel].discard(ws)
        if not _channels[channel]:
            _channels.pop(channel, None)


def broadcast_ws(channel: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget broadcast. Safe to call from sync MCP handlers.

    Uses the running event loop to schedule sends. If no loop is running
    (shouldn't happen during request handling), drops the message and logs.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("broadcast_ws called outside event loop, dropping payload for %s", channel)
        return
    loop.create_task(_broadcast(channel, payload))


async def _broadcast(channel: str, payload: dict[str, Any]) -> None:
    msg = json.dumps(payload)
    async with _lock:
        sockets = list(_channels.get(channel, ()))
    for ws in sockets:
        try:
            await ws.send_text(msg)
        except Exception as e:
            logger.warning("ws send failed on %s: %s", channel, e)
            await unregister_channel(channel, ws)
