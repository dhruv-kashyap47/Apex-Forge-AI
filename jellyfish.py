"""Small subset of jellyfish used by the resolver."""

from __future__ import annotations


_MAP = str.maketrans(
    {
        "b": "1",
        "f": "1",
        "p": "1",
        "v": "1",
        "c": "2",
        "g": "2",
        "j": "2",
        "k": "2",
        "q": "2",
        "s": "2",
        "x": "2",
        "z": "2",
        "d": "3",
        "t": "3",
        "l": "4",
        "m": "5",
        "n": "5",
        "r": "6",
    }
)


def metaphone(text: str) -> str:
    """Very small metaphone-like approximation.

    Good enough for demo blocking logic when the external dependency is missing.
    """

    if not text:
        return ""
    cleaned = "".join(ch.lower() for ch in text if ch.isalpha())
    if not cleaned:
        return ""
    first = cleaned[0].upper()
    encoded = cleaned[1:].translate(_MAP)
    result = []
    prev = None
    for char in encoded:
        if char != prev:
            result.append(char)
        prev = char
    return first + "".join(result)[:6]
