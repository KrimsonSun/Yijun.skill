"""Monopoly game — MCP tools.

Apply phase copies this to backend/games/monopoly/tools.py and registers via
backend/mcp/server.py boot:
    from backend.games.monopoly import tools as monopoly_tools
    monopoly_tools.register(registry)

State persistence is in-memory keyed by conversation_id. If Yijun later wants
multi-device, swap _STATE_BY_CONV for a Postgres table without touching tools.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.mcp.server import MCPRegistry, MCPTool, ToolError, ToolType
from backend.realtime import broadcast_ws

_PLUGIN_ID = "monopoly"
_GAME_CHANNEL = lambda cid: f"/ws/games/monopoly/{cid}"
_LIVE2D_CHANNEL = lambda cid: f"/ws/live2d/{cid}"

_MANIFEST = json.loads(
    (Path(__file__).resolve().parent / "manifest.json").read_text(encoding="utf-8")
)
_REACTIONS = _MANIFEST.get("live2d_reactions", {})

_BOARD_TEMPLATE = [
    {"name": "起点",    "type": "start",    "owner": None, "price": 0},
    {"name": "樱花街",  "type": "property", "owner": None, "price": 100},
    {"name": "粉色咖啡馆","type": "property", "owner": None, "price": 150},
    {"name": "机会",    "type": "chance",   "owner": None, "price": 0},
    {"name": "玫瑰花园","type": "property", "owner": None, "price": 200},
    {"name": "贴贴亭",  "type": "rest",     "owner": None, "price": 0},
    {"name": "草莓铺",  "type": "property", "owner": None, "price": 180},
    {"name": "机会",    "type": "chance",   "owner": None, "price": 0},
    {"name": "月亮塔",  "type": "property", "owner": None, "price": 250},
    {"name": "心愿池",  "type": "rest",     "owner": None, "price": 0},
    {"name": "甜品工坊","type": "property", "owner": None, "price": 220},
    {"name": "拥抱广场","type": "property", "owner": None, "price": 300},
]

_STATE_BY_CONV: dict[str, dict[str, Any]] = {}


# ─── helpers ─────────────────────────────────────────────────────────────

def _load(conversation_id: str) -> dict[str, Any]:
    state = _STATE_BY_CONV.get(conversation_id)
    if state is None:
        raise ToolError("Monopoly is not mounted for this conversation. Call mount_game first.")
    if state["status"] == "ended":
        raise ToolError("Game already ended. Call mount_game to start a new one.")
    return state


def _save(conversation_id: str, state: dict[str, Any]) -> None:
    _STATE_BY_CONV[conversation_id] = state
    broadcast_ws(_GAME_CHANNEL(conversation_id), {"event": "state", "state": state})


def _fire_live2d(conversation_id: str, event: str) -> None:
    reaction = _REACTIONS.get(event)
    if not reaction:
        return
    if "motion" in reaction:
        broadcast_ws(
            _LIVE2D_CHANNEL(conversation_id),
            {"event": "play_motion", "name": reaction["motion"], "fade_ms": 300},
        )
    if "expression" in reaction:
        broadcast_ws(
            _LIVE2D_CHANNEL(conversation_id),
            {"event": "set_expression", "name": reaction["expression"], "hold_ms": 2500},
        )


def _new_game() -> dict[str, Any]:
    return {
        "status": "active",
        "board": [dict(tile) for tile in _BOARD_TEMPLATE],
        "players": [
            {"id": "user", "display_name": "你",   "position": 0, "money": 1500},
            {"id": "emma", "display_name": "Emma", "position": 0, "money": 1500},
        ],
        "turn": "user",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_roll": None,
        "winner": None,
    }


# ─── tool handlers ───────────────────────────────────────────────────────

def _mount_game(conversation_id: str, args: dict) -> dict:
    if args.get("id") != _PLUGIN_ID:
        raise ToolError(f"Wrong plugin id; expected {_PLUGIN_ID}")
    state = _new_game()
    _save(conversation_id, state)
    _fire_live2d(conversation_id, "mount")
    return {"mounted": _PLUGIN_ID, "starting_player": state["turn"]}


def _roll_dice(conversation_id: str, args: dict) -> dict:
    state = _load(conversation_id)
    a, b = random.randint(1, 6), random.randint(1, 6)
    state["last_roll"] = [a, b]
    _save(conversation_id, state)
    _fire_live2d(conversation_id, "roll")
    return {"dice": [a, b], "sum": a + b, "player": state["turn"]}


def _move_token(conversation_id: str, args: dict) -> dict:
    state = _load(conversation_id)
    player_id = args.get("player_id", state["turn"])
    steps = args.get("steps")
    if steps is None and state.get("last_roll"):
        steps = sum(state["last_roll"])
    if not isinstance(steps, int) or steps < 1:
        raise ToolError("steps must be a positive integer or last_roll must be set")

    player = next((p for p in state["players"] if p["id"] == player_id), None)
    if not player:
        raise ToolError(f"Unknown player_id {player_id}")

    board_size = len(state["board"])
    looped = (player["position"] + steps) >= board_size
    player["position"] = (player["position"] + steps) % board_size
    if looped:
        player["money"] += 200  # passing-go bonus

    landed = state["board"][player["position"]]
    _save(conversation_id, state)
    _fire_live2d(conversation_id, "move")

    # win condition: laps tracked implicitly — first to loop the board ends the game
    if looped:
        state["status"] = "ended"
        state["winner"] = player_id
        _save(conversation_id, state)
        _fire_live2d(conversation_id, "win" if player_id == "emma" else "lose")
        return {"position": player["position"], "landed": landed, "winner": player_id}

    return {"position": player["position"], "landed": landed, "passed_go": looped}


def _read_board(conversation_id: str, args: dict) -> dict:
    state = _load(conversation_id)
    return {
        "board": state["board"],
        "players": state["players"],
        "turn": state["turn"],
        "last_roll": state.get("last_roll"),
    }


def _end_turn(conversation_id: str, args: dict) -> dict:
    state = _load(conversation_id)
    state["turn"] = "emma" if state["turn"] == "user" else "user"
    state["last_roll"] = None
    _save(conversation_id, state)
    return {"turn": state["turn"]}


def _end_game(conversation_id: str, args: dict) -> dict:
    state = _STATE_BY_CONV.get(conversation_id)
    if not state:
        return {"status": "not_active"}
    state["status"] = "ended"
    _save(conversation_id, state)
    return {"status": "ended"}


# ─── registration ────────────────────────────────────────────────────────

def register(registry: MCPRegistry) -> None:
    registry.add(MCPTool(
        name="mount_game",
        description="Start a mini-game session. Pass id='monopoly' to start 大富翁.",
        type=ToolType.FUNCTION,
        json_schema={
            "type": "object",
            "properties": {"id": {"type": "string", "enum": ["monopoly"]}},
            "required": ["id"],
        },
        handler=_mount_game,
        exposed_to_llm=True,
        plugin_id=_PLUGIN_ID,
    ))
    registry.add(MCPTool(
        name="roll_dice",
        description="Roll two six-sided dice for the current player. Returns dice and sum.",
        type=ToolType.FUNCTION,
        json_schema={"type": "object", "properties": {}, "required": []},
        handler=_roll_dice,
        exposed_to_llm=True,
        plugin_id=_PLUGIN_ID,
    ))
    registry.add(MCPTool(
        name="move_token",
        description="Move a player by `steps` (defaults to last_roll sum). Returns landed tile.",
        type=ToolType.FUNCTION,
        json_schema={
            "type": "object",
            "properties": {
                "player_id": {"type": "string", "enum": ["user", "emma"]},
                "steps": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            "required": [],
        },
        handler=_move_token,
        exposed_to_llm=True,
        plugin_id=_PLUGIN_ID,
    ))
    registry.add(MCPTool(
        name="read_board",
        description="Return current board state, players, turn, last roll.",
        type=ToolType.FUNCTION,
        json_schema={"type": "object", "properties": {}, "required": []},
        handler=_read_board,
        exposed_to_llm=True,
        plugin_id=_PLUGIN_ID,
    ))
    registry.add(MCPTool(
        name="end_turn",
        description="Pass the turn to the other player.",
        type=ToolType.FUNCTION,
        json_schema={"type": "object", "properties": {}, "required": []},
        handler=_end_turn,
        exposed_to_llm=True,
        plugin_id=_PLUGIN_ID,
    ))
    registry.add(MCPTool(
        name="end_game",
        description="End the current 大富翁 session.",
        type=ToolType.FUNCTION,
        json_schema={"type": "object", "properties": {}, "required": []},
        handler=_end_game,
        exposed_to_llm=True,
        plugin_id=_PLUGIN_ID,
    ))
