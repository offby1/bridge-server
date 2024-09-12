from __future__ import annotations

import contextlib
import sys

import bridge.seat
from django.db import connection

# {1: 'NORTH', 2: 'EAST', 3: 'SOUTH', 4: 'WEST'}
SEAT_CHOICES: dict[int, str] = {v.value: k for k, v in bridge.seat.Seat.__members__.items()}


from .board import Board  # noqa
from .handrecord import AuctionException, Call, HandRecord, Play  # noqa
from .message import Message  # noqa
from .player import (  # noqa
    PartnerException,
    Player,
    PlayerException,
)
from .seat import Seat, SeatException  # noqa
from .table import Table, TableException  # noqa


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
