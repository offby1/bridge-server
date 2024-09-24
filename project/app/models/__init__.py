from __future__ import annotations

import contextlib
import sys

from django.db import connection

from .board import Board
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
    "SEAT_CHOICES",
]


class QueryLogger:
    def __init__(self, name=None):
        self.prefix = f"{name}: " if name is not None else ""

    def __call__(self, execute, sql, params, many, context):
        sys.stdout.write(f"{self.prefix}{sql} {params}\n")
        return execute(sql, params, many, context)


@contextlib.contextmanager
def logged_queries(name=None):
    ql = QueryLogger(name=name)
    with connection.execute_wrapper(ql):
        yield
