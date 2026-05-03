"""Minimal tqdm shim."""

from __future__ import annotations

from typing import Iterable, Iterator, TypeVar

T = TypeVar("T")


def tqdm(iterable: Iterable[T], *_, **__) -> Iterator[T]:
    return iter(iterable)

