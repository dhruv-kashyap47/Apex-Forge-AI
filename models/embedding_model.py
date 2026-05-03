"""
ApexForge AI — Embedding Model
Single-load, cached sentence-transformer model for generating 384-dim vectors.
Runs 100% locally — no API calls, no PII leaves the machine.
"""

from __future__ import annotations

import os
import threading
from typing import ClassVar

import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
_EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", 384))


class EmbeddingModel:
    """
    Thread-safe singleton wrapper around SentenceTransformer.
    The model is loaded once and reused across all Streamlit sessions.
    """

    _instance:   ClassVar[EmbeddingModel | None] = None
    _lock:       ClassVar[threading.Lock]         = threading.Lock()

    def __init__(self) -> None:
        logger.info(f"Loading embedding model: {_MODEL_NAME}…")
        self._model = SentenceTransformer(_MODEL_NAME)
        logger.info("Embedding model ready.")

    # ── Singleton factory ─────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "EmbeddingModel":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:       # double-checked locking
                    cls._instance = cls()
        return cls._instance

    # ── Core API ──────────────────────────────────────────────────────────

    def encode(self, text: str) -> list[float]:
        """Encode a single string → 384-dim float list (normalised)."""
        vec = self._model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vec.tolist()

    def encode_batch(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Batch encode for throughput during seeding (uses GPU if available)."""
        vecs = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 100,
        )
        return vecs.tolist()

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Fast cosine similarity (vectors already normalised → dot product)."""
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        # Clamp to [0, 1] — normalised vectors won't exceed this
        return float(np.clip(np.dot(va, vb), 0.0, 1.0))

    @staticmethod
    def build_record_text(record: dict) -> str:
        """
        Construct the canonical text representation of a business record
        for embedding.  This is the single most important design choice —
        consistent field ordering + normalisation before embedding.
        """
        parts = [
            (record.get("normalized_name") or record.get("business_name") or "").strip(),
            (record.get("sector") or "").strip(),
            (record.get("pin_code") or "").strip(),
            (record.get("address") or "")[:80].strip(),     # truncate long addresses
            (record.get("department_code") or "").strip(),
        ]
        return " | ".join(p for p in parts if p)


# Convenience module-level accessor
def get_model() -> EmbeddingModel:
    return EmbeddingModel.get()
