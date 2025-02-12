from __future__ import annotations

import collections
import contextlib
import dataclasses
import logging
import time
from typing import Any

from django.db import connection

from .board import Board
from .common import SEAT_CHOICES
from .hand import AuctionError, Call, Hand, HandError, Play
from .message import Message
from .player import (
    PartnerException,
    Player,
    PlayerException,
)
from .seat import Seat, SeatException
from .table import NoMoreBoards, Table, TableException
from .tournament import Tournament

__all__ = [
    "Board",
    "AuctionError",
    "Call",
    "Hand",
    "HandError",
    "Play",
    "Message",
    "NoMoreBoards",
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

        start_time = time.time()
        try:
            rv = execute(sql, params, many, context)
        finally:
            stop_time = time.time()

        self.counter[sql] += stop_time - start_time

        return rv


@contextlib.contextmanager
def logged_queries():
    ql = QueryLogger()
    with connection.execute_wrapper(ql):
        yield ql
