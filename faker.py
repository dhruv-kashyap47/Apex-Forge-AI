"""Lightweight Faker shim for offline demo generation."""

from __future__ import annotations

import random


class Faker:
    def __init__(self, locale: str | None = None) -> None:
        self.locale = locale or "en_IN"
        self._rng = random.Random(42)

    def phone_number(self) -> str:
        blocks = [self._rng.randint(600, 999), self._rng.randint(100, 999), self._rng.randint(1000, 9999)]
        return f"+91-{blocks[0]}-{blocks[1]}-{blocks[2]}"

    def company(self) -> str:
        names = ["Apex Industries", "Forge Tech", "Karnataka Traders", "Bengaluru Works"]
        return self._rng.choice(names)
