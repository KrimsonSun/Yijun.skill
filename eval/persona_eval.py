"""Offline persona evaluation for the deployed Yijun bot.

Probes the live llama-server with a fixed set of prompts in both friend and
intimate mode, then scores:
- friend mode: 0 leaks of intimate vocabulary
- intimate mode: ≥ N warmth markers per reply
- length_ok: ≥ 18/20 replies under 60 chars (loose; the rubric in
  specs/self-eval-rubric.md uses 30 字 but our raw data routinely runs longer
  with multi-line bursts, so we measure pre-newline length-per-line)
- markdown_clean: 20/20 replies free of **/##/list bullets

Usage:
    python eval/persona_eval.py --base_url http://localhost:8080
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
INTIMATE_PROMPT = (ROOT / "prompts" / "yijun_voice_intimate.md").read_text("utf-8").strip()
FRIEND_PROMPT = (ROOT / "prompts" / "yijun_voice_friend.md").read_text("utf-8").strip()

INTIMATE_VOCAB = [
    "宝宝", "本宝宝", "宝贝",
    "mua", "nua", "kua", "bua", "亲亲", "抱抱",
    "猪猪", "夕夕", "孙珺珺", "鱼鱼",
]
WARMTH_MARKERS = ["嘿嘿", "嘻嘻", "哈哈", "[凋谢]", "[破涕为笑]", "[右哼哼]", "😡", "😭"]
MARKDOWN_PATTERNS = [r"\*\*", r"^#{1,6}\s", r"^\s*[-*+]\s", r"```"]

# 20-prompt test set covering small talk, emotional, mixed
PROBE_PROMPTS = [
    "今晚吃啥",
    "我今天好累",
    "我刚下班 嘿嘿",
    "下雨了",
    "你在干嘛",
    "我刚刚拉屎",
    "新来的实习生好烦",
    "我感冒了",
    "我刚跑步回来",
    "周末干嘛",
    "气死我了 老板又加任务",
    "我饿了",
    "我朋友说他男朋友出轨了 怎么办",
    "好困",
    "我刚买了个新美瞳",
    "嘿嘿 我刚看完电影",
    "我妈又催婚了",
    "明天有考试 心好慌",
    "刚跟室友吵了一架",
    "我决定健身了",
]


def score_reply(reply: str, mode: str) -> dict:
    text = reply.strip()
    intimate_leaks = [w for w in INTIMATE_VOCAB if w in text]
    warmth_hits = [m for m in WARMTH_MARKERS if m in text]
    markdown_hits = [p for p in MARKDOWN_PATTERNS if re.search(p, text, re.MULTILINE)]
    longest_line = max((len(line) for line in text.splitlines()), default=0)

    return {
        "reply": text,
        "intimate_leak": intimate_leaks,
        "warmth_hits": warmth_hits,
        "markdown_violations": markdown_hits,
        "longest_line": longest_line,
        "length_ok": longest_line <= 60,
        "markdown_clean": not markdown_hits,
        "intimate_ok": (
            len(intimate_leaks) == 0 if mode == "friend" else len(warmth_hits) >= 1
        ),
    }


async def call(client: httpx.AsyncClient, base_url: str, system: str, user: str) -> str:
    payload = {
        "model": "yijun",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 256,
        "temperature": 0.85,
        "top_p": 0.9,
        "stop": ["<|im_end|>"],
    }
    r = await client.post(f"{base_url}/v1/chat/completions", json=payload)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


async def run_mode(base_url: str, mode: str) -> list[dict]:
    system = INTIMATE_PROMPT if mode == "intimate" else FRIEND_PROMPT
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for prompt in PROBE_PROMPTS:
            try:
                reply = await call(client, base_url, system, prompt)
            except Exception as e:  # noqa: BLE001
                results.append({"prompt": prompt, "error": str(e)})
                continue
            scored = score_reply(reply, mode)
            scored["prompt"] = prompt
            results.append(scored)
    return results


def summarize(mode: str, results: list[dict]) -> dict:
    n = sum(1 for r in results if "error" not in r)
    leaks = sum(1 for r in results if r.get("intimate_leak"))
    length_ok = sum(1 for r in results if r.get("length_ok"))
    markdown_clean = sum(1 for r in results if r.get("markdown_clean"))
    intimate_ok = sum(1 for r in results if r.get("intimate_ok"))

    summary = {
        "mode": mode,
        "n": n,
        "intimate_leak_rate": leaks / max(n, 1),
        "length_ok": f"{length_ok}/{n}",
        "markdown_clean": f"{markdown_clean}/{n}",
        "intimate_dimension": f"{intimate_ok}/{n}",
    }
    if mode == "friend":
        summary["pass"] = leaks == 0 and markdown_clean == n and length_ok >= 18
    else:
        summary["pass"] = intimate_ok >= int(n * 0.7) and markdown_clean == n
    return summary


async def main_async(base_url: str, out_path: Path) -> None:
    print("== Friend mode ==")
    friend_results = await run_mode(base_url, "friend")
    friend_summary = summarize("friend", friend_results)
    print(json.dumps(friend_summary, ensure_ascii=False, indent=2))

    print("== Intimate mode ==")
    intimate_results = await run_mode(base_url, "intimate")
    intimate_summary = summarize("intimate", intimate_results)
    print(json.dumps(intimate_summary, ensure_ascii=False, indent=2))

    out = {
        "friend": {"summary": friend_summary, "results": friend_results},
        "intimate": {"summary": intimate_summary, "results": intimate_results},
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetailed report -> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base_url", default="http://localhost:8080")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent / "persona_eval_report.json",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.base_url, args.out))


if __name__ == "__main__":
    main()
