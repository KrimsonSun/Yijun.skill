"""Thin client for llama-server's OpenAI-compatible /v1/chat/completions."""
from __future__ import annotations

import httpx


class LlamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        model: str = "yijun",
        timeout_s: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    async def chat(
        self,
        messages: list[dict],
        max_tokens: int = 256,
        temperature: float = 0.85,
        top_p: float = 0.9,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stop": ["<|im_end|>", "<|endoftext|>"],
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"].strip()
