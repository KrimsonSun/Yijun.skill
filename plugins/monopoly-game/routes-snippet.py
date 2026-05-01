"""Monopoly REST + WS routes.

Apply phase copies this to backend/api/routes/monopoly.py and adds
`app.include_router(monopoly.router)` to backend/main.py.

REST endpoint allows GamePanel.jsx to fetch initial state on mount.
WS channel pushes state diffs as tools mutate the game.
"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.games.monopoly.tools import _STATE_BY_CONV  # type: ignore[attr-defined]
from backend.realtime import register_channel, unregister_channel

router = APIRouter()


@router.get("/games/monopoly/state")
def get_state(conversation_id: str) -> dict:
    state = _STATE_BY_CONV.get(conversation_id)
    if state is None:
        raise HTTPException(status_code=404, detail="not_mounted")
    return state


@router.websocket("/ws/games/monopoly/{conversation_id}")
async def monopoly_ws(websocket: WebSocket, conversation_id: str):
    channel = f"/ws/games/monopoly/{conversation_id}"
    await websocket.accept()
    await register_channel(channel, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await unregister_channel(channel, websocket)
