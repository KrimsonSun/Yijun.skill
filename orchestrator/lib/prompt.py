#!/usr/bin/env python3
"""Render `prompts/system-prompt.template.md` against the current distillates,
plugin manifests, and rubric format.

Invoked by `orchestrator/emit.sh`. Pure-Python; no Claude needed for this step.

Usage:
    python orchestrator/lib/prompt.py \
        --skill-root /path/to/Yijun.skill \
        --character emma \
        --games monopoly \
        --output /path/to/bundle/system-prompt.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

PLACEHOLDERS = (
    "{{persona_block}}",
    "{{available_tools}}",
    "{{available_games}}",
    "{{rubric_format}}",
    "{{tool_call_examples}}",
)


# ─── helpers ──────────────────────────────────────────────────────────────

def read_text(path: Path) -> str:
    if not path.exists():
        sys.exit(f"prompt.py: missing required file {path}")
    return path.read_text(encoding="utf-8")


def extract_fenced_block(md: str, fence: str = "```") -> str | None:
    """Return the contents of the first fenced block (any language tag)."""
    lines = md.splitlines()
    in_block = False
    buf: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(fence):
            if in_block:
                return "\n".join(buf)
            in_block = True
            continue
        if in_block:
            buf.append(line)
    return None


def strip_doc_preamble(md: str, first_section_marker: str) -> str:
    """Drop documentation paragraphs before the first content section.

    Used for `prompts/tool-call-examples.md` which has a multi-paragraph
    preamble before the actual examples start.
    """
    idx = md.find(first_section_marker)
    return md[idx:] if idx >= 0 else md


def universal_voice_rules(persona_md: str) -> str:
    """Pull the 'Universal voice rules' code block from distill/persona.md."""
    section_marker = "## Universal voice rules"
    idx = persona_md.find(section_marker)
    if idx < 0:
        sys.exit("distill/persona.md is missing the '## Universal voice rules' section")
    block = extract_fenced_block(persona_md[idx:])
    if not block:
        sys.exit("Could not find a fenced block under 'Universal voice rules'")
    return block.strip()


def character_block(persona_md: str, name: str) -> str:
    """Pull the section for a specific character (Emma/Aria/Sage)."""
    cap = name.capitalize()
    marker = f"## {cap} —"
    idx = persona_md.find(marker)
    if idx < 0:
        sys.exit(f"distill/persona.md has no section starting with '{marker}'")
    block = extract_fenced_block(persona_md[idx:])
    if not block:
        sys.exit(f"Could not find a fenced block under {marker}")
    return block.strip()


def render_persona(skill_root: Path, character: str) -> str:
    persona_md = read_text(skill_root / "distill" / "persona.md")
    universal = universal_voice_rules(persona_md)
    char = character_block(persona_md, character)
    return f"{universal}\n\n— 当前人格 —\n\n{char}"


def render_available_tools(skill_root: Path, games: Iterable[str]) -> str:
    """Concatenate Live2D tools (always on) + each enabled game's tools."""
    tools_md: list[str] = []

    # Live2D — always present after Phase 2 lands
    live2d_manifest = skill_root / "plugins" / "live2d-mcp" / "manifest.json"
    if live2d_manifest.exists():
        m = json.loads(live2d_manifest.read_text(encoding="utf-8"))
        for t in m.get("tools", []):
            tools_md.append(f"- `{t['name']}({_param_hint(t)})` — {t['description']}")

    # Per-game tools
    for game_id in games:
        game_manifest = skill_root / "plugins" / f"{game_id}-game" / "manifest.json"
        if not game_manifest.exists():
            continue
        m = json.loads(game_manifest.read_text(encoding="utf-8"))
        # Game tools live in their mcp-tools.py — for the LLM tool list we
        # use the tool names declared in manifest.json + a brief stub.
        for tool_name in m.get("mcp_tools", []):
            tools_md.append(f"- `{tool_name}(...)` — {m['display_name'].get('cn', game_id)} 游戏工具")

    if not tools_md:
        return "(尚未注册任何工具)"
    return "\n".join(tools_md)


def _param_hint(tool: dict) -> str:
    schema = tool.get("json_schema", {})
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    parts = []
    for name in props:
        parts.append(name if name in required else f"{name}?")
    return ", ".join(parts)


def render_available_games(skill_root: Path, games: Iterable[str]) -> str:
    fragments: list[str] = []
    for game_id in sorted(games):
        frag_path = skill_root / "plugins" / f"{game_id}-game" / "system-prompt-fragment.md"
        if frag_path.exists():
            fragments.append(frag_path.read_text(encoding="utf-8").strip())
    if not fragments:
        return "(尚无小游戏可玩)"
    return "\n\n".join(fragments)


def render_rubric_format(skill_root: Path) -> str:
    rubric_md = read_text(skill_root / "specs" / "self-eval-rubric.md")
    block = extract_fenced_block_after(rubric_md, "## Per-turn rubric")
    if not block:
        sys.exit("specs/self-eval-rubric.md missing per-turn JSON example")
    return f"```json\n{block.strip()}\n```"


def extract_fenced_block_after(md: str, marker: str) -> str | None:
    idx = md.find(marker)
    if idx < 0:
        return None
    return extract_fenced_block(md[idx:])


def render_examples(skill_root: Path) -> str:
    raw = read_text(skill_root / "prompts" / "tool-call-examples.md")
    # Skip the doc preamble before the first "## Example".
    return strip_doc_preamble(raw, "## Example").strip()


# ─── main ─────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-root", type=Path, required=True)
    ap.add_argument("--character", default="emma")
    ap.add_argument("--games", default="", help="comma-separated game ids (e.g. monopoly)")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    games = [g.strip() for g in args.games.split(",") if g.strip()]

    template_full = read_text(args.skill_root / "prompts" / "system-prompt.template.md")
    template = extract_fenced_block(template_full)
    if not template:
        sys.exit("prompts/system-prompt.template.md missing the prompt fenced block")

    rendered = template
    rendered = rendered.replace("{{persona_block}}",      render_persona(args.skill_root, args.character))
    rendered = rendered.replace("{{available_tools}}",    render_available_tools(args.skill_root, games))
    rendered = rendered.replace("{{available_games}}",    render_available_games(args.skill_root, games))
    rendered = rendered.replace("{{rubric_format}}",      render_rubric_format(args.skill_root))
    rendered = rendered.replace("{{tool_call_examples}}", render_examples(args.skill_root))

    # Any remaining `{{placeholder}}` is either (a) literal text inside an
    # injected example or (b) a real unfilled placeholder. We can't tell from
    # here, so warn loudly but don't fail — the LLM will treat literal `{{...}}`
    # as harmless prose.
    import re
    surviving = sorted(set(re.findall(r"\{\{[a-z_]+\}\}", rendered)))
    if surviving:
        print(f"WARN: '{{{{...}}}}' literals remain in rendered output (likely inside few-shot text): {surviving}",
              file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(str(args.output))


if __name__ == "__main__":
    main()
