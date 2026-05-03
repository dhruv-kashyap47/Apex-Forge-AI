"""Deterministic offline SentenceTransformer shim."""

from __future__ import annotations

import hashlib
from typing import Iterable

import numpy as np


class SentenceTransformer:
    """A tiny hashing-based embedding model.

    It preserves the API shape needed by the project while avoiding the
    heavyweight external dependency and model download.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or "offline-hash-encoder"

    def _encode_one(self, text: str, dim: int = 384) -> np.ndarray:
        vec = np.zeros(dim, dtype=np.float32)
        if not text:
            return vec
        tokens = [tok for tok in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if tok]
        if not tokens:
            tokens = [text.lower()]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for offset in range(0, 32, 4):
                idx = int.from_bytes(digest[offset : offset + 4], "big") % dim
                vec[idx] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec

    def encode(
        self,
        texts: str | Iterable[str],
        batch_size: int | None = None,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
        **_: object,
    ) -> np.ndarray:
        if isinstance(texts, str):
            vec = self._encode_one(texts)
            return vec

        vectors = [self._encode_one(text) for text in texts]
        result = np.vstack(vectors) if vectors else np.zeros((0, 384), dtype=np.float32)
        if normalize_embeddings and len(result):
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            result = result / norms
        return result

