"""BGE-small-zh retrieval over the 23k-message training corpus.

Builds an in-memory FAISS index of "user turn -> assistant reply" pairs from
finetune_clean.jsonl. At query time we embed the new user message and return
the top-k most similar pairs as few-shot examples.

In friend mode we drop pairs where the assistant reply contains intimate
vocabulary (so the model doesn't see "宝宝/mua/猪猪" as exemplars).
"""
from __future__ import annotations

import json
import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

INTIMATE_TOKENS = (
    "宝宝", "本宝宝", "宝贝",
    "mua", "nua", "kua", "bua", "亲亲", "抱抱",
    "猪猪", "夕夕", "孙珺珺", "鱼鱼",
    "miamia", "muamua",
)


@dataclass
class Pair:
    user: str
    assistant: str
    is_intimate: bool


def is_intimate_text(text: str) -> bool:
    return any(tok in text for tok in INTIMATE_TOKENS)


def extract_pairs(jsonl_path: Path) -> list[Pair]:
    pairs: list[Pair] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            msgs = obj.get("messages", [])
            for i in range(len(msgs) - 1):
                if msgs[i]["role"] == "user" and msgs[i + 1]["role"] == "assistant":
                    u = msgs[i]["content"].strip()
                    a = msgs[i + 1]["content"].strip()
                    if not u or not a:
                        continue
                    pairs.append(Pair(user=u, assistant=a, is_intimate=is_intimate_text(a)))
    return pairs


class Retrieval:
    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        index_dir: Path | str = "bot/.index",
    ) -> None:
        self.index_dir = Path(index_dir)
        self.model_name = model_name
        self.model: SentenceTransformer | None = None
        self.index: faiss.Index | None = None
        self.pairs: list[Pair] = []

    def _ensure_model(self) -> SentenceTransformer:
        if self.model is None:
            self.model = SentenceTransformer(self.model_name)
        return self.model

    def build(self, jsonl_path: Path) -> None:
        pairs = extract_pairs(jsonl_path)
        logger.info("Extracted %d (user, assistant) pairs", len(pairs))
        if not pairs:
            raise RuntimeError(f"No pairs extracted from {jsonl_path}")

        model = self._ensure_model()
        texts = [p.user for p in pairs]
        embs = model.encode(
            texts,
            batch_size=64,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        ).astype("float32")

        index = faiss.IndexFlatIP(embs.shape[1])  # cosine via normalized inner product
        index.add(embs)

        self.index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(self.index_dir / "pairs.faiss"))
        with (self.index_dir / "pairs.pkl").open("wb") as f:
            pickle.dump(pairs, f)
        logger.info("Wrote index + pairs to %s", self.index_dir)

        self.index = index
        self.pairs = pairs

    def load(self) -> None:
        self.index = faiss.read_index(str(self.index_dir / "pairs.faiss"))
        with (self.index_dir / "pairs.pkl").open("rb") as f:
            self.pairs = pickle.load(f)
        self._ensure_model()
        logger.info("Loaded index with %d pairs", len(self.pairs))

    def search(
        self,
        query: str,
        k: int = 3,
        exclude_intimate: bool = False,
    ) -> list[Pair]:
        if self.index is None or not self.pairs:
            raise RuntimeError("Retrieval not loaded; call build() or load() first")
        model = self._ensure_model()
        q = model.encode(
            [query], normalize_embeddings=True, convert_to_numpy=True
        ).astype("float32")
        # Over-fetch to allow filtering
        fetch_k = k * 4 if exclude_intimate else k
        scores, idxs = self.index.search(q, fetch_k)
        results: list[Pair] = []
        for idx in idxs[0]:
            if idx < 0:
                continue
            pair = self.pairs[idx]
            if exclude_intimate and pair.is_intimate:
                continue
            results.append(pair)
            if len(results) >= k:
                break
        return results


def main() -> None:
    """CLI: build the index from finetune_clean.jsonl."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--jsonl",
        type=Path,
        default=Path(__file__).parent.parent / "source_data" / "finetune_clean.jsonl",
    )
    parser.add_argument(
        "--index_dir",
        type=Path,
        default=Path(__file__).parent / ".index",
    )
    args = parser.parse_args()

    r = Retrieval(index_dir=args.index_dir)
    r.build(args.jsonl)


if __name__ == "__main__":
    main()
