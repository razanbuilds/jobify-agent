"""Tiny pure-Python BM25 so retrieval works offline. Swap in bm25s / embeddings later if you like."""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from . import config

_TOKEN = re.compile(r"\w+", re.UNICODE)
STOP = {"a", "an", "the", "in", "of", "for", "to", "and", "or", "me", "my", "find", "show",
        "jobs", "job", "roles", "role", "with", "is", "are", "i", "on", "at", "by"}


def tokenize(text: str) -> list[str]:
    return [t for t in (w.lower() for w in _TOKEN.findall(text or "")) if t not in STOP]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.N = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.N) if self.N else 0.0
        self.tf = [Counter(d) for d in docs]
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def scores(self, query_tokens: list[str]) -> list[float]:
        out = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i]) or 1
            s = 0.0
            for t in query_tokens:
                f = tf.get(t, 0)
                if f:
                    norm = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                    s += self.idf[t] * f * (self.k1 + 1) / norm
            out.append(s)
        return out


class ProfileIndex:
    """Chunks data/profile/*.md by paragraph and searches them with BM25."""

    def __init__(self, directory: Path | None = None):
        d = Path(directory or config.DATA_DIR / "profile")
        self.chunks: list[dict] = []
        for f in sorted(d.glob("*.md")):
            for block in re.split(r"\n\s*\n", f.read_text(encoding="utf-8")):
                block = block.strip()
                if block and not block.startswith("<!--"):
                    self.chunks.append({"source": f.name, "text": block})
        self.bm25 = BM25([tokenize(c["text"]) for c in self.chunks])

    def search(self, query: str, k: int = 3) -> list[dict]:
        scores = self.bm25.scores(tokenize(query))
        ranked = sorted(zip(scores, self.chunks), key=lambda x: -x[0])
        return [
            {"source": c["source"], "text": c["text"][:400], "score": round(s, 3)}
            for s, c in ranked[:k]
            if s > 0
        ]
