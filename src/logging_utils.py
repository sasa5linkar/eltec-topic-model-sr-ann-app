"""Lightweight structured logging helpers."""

from __future__ import annotations

import json
import logging
from typing import Any


def get_logger(name: str = "eltec_app") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def log_event(logger: logging.Logger, level: str, event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    line = json.dumps(payload, ensure_ascii=False)
    getattr(logger, level.lower(), logger.info)(line)
