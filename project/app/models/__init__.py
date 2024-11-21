from __future__ import annotations

import collections
import contextlib
import dataclasses
import logging
from typing import Any

from django.db import connection

from .board import Board, Tournament
from .common import SEAT_CHOICES
from .hand import AuctionError, Call, Hand, Play
from .message import Message
from .player import (
    PartnerException,
    Player,
    PlayerException,
)
from .seat import Seat, SeatException
from .table import Table, TableException

__all__ = [
    "Board",
    "AuctionError",
    "Call",
    "Hand",
    "Play",
    "Message",
    "PartnerException",
    "Player",
    "PlayerException",
    "Seat",
    "SeatException",
    "Table",
    "TableException",
    "Tournament",
    "SEAT_CHOICES",
]


logger = logging.getLogger(__name__)


@dataclasses.dataclass
class QueryLogger:
    calls: list[tuple[Any]] = dataclasses.field(default_factory=list)
    counter: collections.Counter = dataclasses.field(default_factory=collections.Counter)

    def __call__(self, execute, sql, params, many, context):
        self.calls.append((sql, params, many, context))
        self.counter[sql] += 1

        logger.info(f"{sql} {params=}")

        return execute(sql, params, many, context)


@contextlib.contextmanager
def logged_queries():
    ql = QueryLogger()
    with connection.execute_wrapper(ql):
        yield ql
