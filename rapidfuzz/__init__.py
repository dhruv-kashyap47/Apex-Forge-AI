"""Minimal rapidfuzz shim exposing fuzz helpers."""

from __future__ import annotations

from difflib import SequenceMatcher


def _normalize(text: str) -> str:
    return " ".join(str(text).lower().split())


class _Fuzz:
    @staticmethod
    def token_sort_ratio(a: str, b: str) -> float:
        tokens_a = " ".join(sorted(_normalize(a).split()))
        tokens_b = " ".join(sorted(_normalize(b).split()))
        return SequenceMatcher(None, tokens_a, tokens_b).ratio() * 100.0

    @staticmethod
    def partial_ratio(a: str, b: str) -> float:
        a_n = _normalize(a)
        b_n = _normalize(b)
        if not a_n or not b_n:
            return 0.0
        if len(a_n) > len(b_n):
            a_n, b_n = b_n, a_n
        best = 0.0
        span = len(a_n)
        for i in range(0, max(len(b_n) - span + 1, 1)):
            window = b_n[i : i + span]
            best = max(best, SequenceMatcher(None, a_n, window).ratio())
        return best * 100.0


fuzz = _Fuzz()

