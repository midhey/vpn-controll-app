"""Базовая настройка логирования.

Секреты (пароли, agent secret, SSH-доступы, конфиги/vpn_url) в логи не пишутся —
это ответственность вызывающего кода, здесь только формат.
"""

from __future__ import annotations

import logging


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
