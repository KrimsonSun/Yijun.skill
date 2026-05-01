"""Live2D WebSocket route — pushes motion/expression events to the frontend canvas.

Apply phase copies this to backend/api/routes/live2d_ws.py (separate from the
existing live2d.py which serves model files) and adds
`app.include_router(live2d_ws.router)` to backend/main.py.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.realtime import register_channel, unregister_channel  # added by Phase 2

router = APIRouter()


@router.websocket("/ws/live2d/{conversation_id}")
async def live2d_ws(websocket: WebSocket, conversation_id: str):
    channel = f"/ws/live2d/{conversation_id}"
    await websocket.accept()
    await register_channel(channel, websocket)
    try:
        while True:
            # We don't expect messages from the client — this is push-only.
            # Keep the connection alive; bail on disconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await unregister_channel(channel, websocket)
