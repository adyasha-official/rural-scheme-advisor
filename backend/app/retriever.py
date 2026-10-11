"""Vector search over the saved index (numpy cosine similarity).
For a few thousand chunks this is fast and avoids a separate database to host."""
import json
from dataclasses import dataclass

import numpy as np

from . import config


@dataclass
class Hit:
    chunk: dict
    score: float


class Index:
    def __init__(self, chunks: list[dict], vectors: np.ndarray):
        self.chunks = chunks
        self.vectors = vectors

    @classmethod
    def load(cls) -> "Index | None":
        emb, meta = config.INDEX_DIR / "embeddings.npy", config.INDEX_DIR / "chunks.json"
        if not emb.exists() or not meta.exists():
            return None
        return cls(json.loads(meta.read_text(encoding="utf-8")), np.load(emb))

    def search(
        self, query_vec: np.ndarray, k: int = 5, scheme_id: str | None = None, min_score: float = 0.0
    ) -> list[Hit]:
        scores = self.vectors @ query_vec  # vectors are L2-normalised -> cosine
        if scheme_id:
            mask = np.array([c["scheme_id"] == scheme_id for c in self.chunks])
            scores = np.where(mask, scores, -1.0)
        order = np.argsort(-scores)[:k]
        return [Hit(self.chunks[i], float(scores[i])) for i in order if scores[i] >= min_score]


_index: Index | None = None


def get_index(reload: bool = False) -> Index | None:
    global _index
    if _index is None or reload:
        _index = Index.load()
    return _index
