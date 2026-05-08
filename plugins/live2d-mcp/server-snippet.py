"""Live2D MCP plugin — exposes play_motion / set_expression to the LLM.

Apply phase copies this file to backend/mcp/plugins/live2d.py and adds
`from backend.mcp.plugins import live2d; live2d.register(registry)` to the
server boot in backend/mcp/server.py.
"""

from pathlib import Path

from backend.mcp.server import MCPRegistry, MCPTool, ToolError, ToolType
from backend.realtime import broadcast_ws  # added by Phase 2 apply

# Source-of-truth motion / expression names — derived at boot from filesystem
# so we never advertise a motion that doesn't exist on disk.
_LIVE2D_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "live2d" / "emma"


def _scan_motions() -> set[str]:
    if not _LIVE2D_DIR.exists():
        return set()
    return {p.stem for p in _LIVE2D_DIR.glob("*.mtn")}


def _scan_expressions() -> set[str]:
    if not _LIVE2D_DIR.exists():
        return set()
    return {p.stem.replace(".exp", "") for p in _LIVE2D_DIR.glob("*.exp.json")}


_MOTION_NAMES = _scan_motions()
_EXPRESSION_NAMES = _scan_expressions()


def _play_motion(conversation_id: str, args: dict) -> dict:
    name = args["name"]
    fade_ms = args.get("fade_ms", 300)
    if name not in _MOTION_NAMES:
        raise ToolError(f"Unknown motion '{name}'. Known: {sorted(_MOTION_NAMES)}")
    broadcast_ws(
        f"/ws/live2d/{conversation_id}",
        {"event": "play_motion", "name": name, "fade_ms": fade_ms},
    )
    return {"status": "queued", "name": name}


def _set_expression(conversation_id: str, args: dict) -> dict:
    name = args["name"]
    hold_ms = args.get("hold_ms", 2000)
    if name not in _EXPRESSION_NAMES:
        raise ToolError(f"Unknown expression '{name}'. Known: {sorted(_EXPRESSION_NAMES)}")
    broadcast_ws(
        f"/ws/live2d/{conversation_id}",
        {"event": "set_expression", "name": name, "hold_ms": hold_ms},
    )
    return {"status": "queued", "name": name}


_PLAY_MOTION_DESC = (
    "Play a named Live2D motion on Emma's avatar. Use to react emotionally — "
    "flickHead_00 for warmth/empathy, shake_00 for distress/concern, "
    "tapBody_00 for excitement/celebration, idle_* for ambient, "
    "pinchIn_*/pinchOut_* for playful pinch."
)

_SET_EXPRESSION_DESC = (
    "Hold a facial expression on Emma's avatar. "
    "f01=neutral resting, f02=happy/warm, f03=sad/worried, f04=surprised/wide-eyed."
)


def register(registry: MCPRegistry) -> None:
    registry.add(
        MCPTool(
            name="play_motion",
            description=_PLAY_MOTION_DESC,
            type=ToolType.FUNCTION,
            json_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": sorted(_MOTION_NAMES)},
                    "fade_ms": {"type": "integer", "default": 300},
                },
                "required": ["name"],
            },
            handler=_play_motion,
            exposed_to_llm=True,
            plugin_id="live2d",
        )
    )
    registry.add(
        MCPTool(
            name="set_expression",
            description=_SET_EXPRESSION_DESC,
            type=ToolType.FUNCTION,
            json_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": sorted(_EXPRESSION_NAMES)},
                    "hold_ms": {"type": "integer", "default": 2000},
                },
                "required": ["name"],
            },
            handler=_set_expression,
            exposed_to_llm=True,
            plugin_id="live2d",
        )
    )
