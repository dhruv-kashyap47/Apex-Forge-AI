"""Tiny loguru shim backed by the standard logging module."""

from __future__ import annotations

import logging


class _Logger:
    def __init__(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
        self._logger = logging.getLogger("apexforge")

    def _format(self, message: str, *args, **kwargs) -> str:
        if args or kwargs:
            try:
                return message.format(*args, **kwargs)
            except Exception:
                pass
        return message

    def info(self, message: str, *args, **kwargs) -> None:
        self._logger.info(self._format(message, *args, **kwargs))

    def warning(self, message: str, *args, **kwargs) -> None:
        self._logger.warning(self._format(message, *args, **kwargs))

    def error(self, message: str, *args, **kwargs) -> None:
        self._logger.error(self._format(message, *args, **kwargs))

    def exception(self, message: str, *args, **kwargs) -> None:
        self._logger.exception(self._format(message, *args, **kwargs))


logger = _Logger()
