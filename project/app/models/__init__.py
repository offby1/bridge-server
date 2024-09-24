from __future__ import annotations

import collections
import contextlib
import sys

import bridge.seat
from django.db import connection

# {1: 'NORTH', 2: 'EAST', 3: 'SOUTH', 4: 'WEST'}
SEAT_CHOICES: dict[int, str] = {v.value: k for k, v in bridge.seat.Seat.__members__.items()}


from .board import Board  # noqa
from .hand import AuctionError, Call, Hand, Play  # noqa
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
        self.calls = []

    def __call__(self, execute, sql, params, many, context):
        self.calls.append((sql, params, many, context))
        return execute(sql, params, many, context)


@contextlib.contextmanager
def logged_queries(name=None):
    ql = QueryLogger(name=name)
    with connection.execute_wrapper(ql):
        yield
    categorized_calls = collections.defaultdict(list)
    for call in ql.calls:
        sql, params, many, context = call
        categorized_calls[sql].append(call)
    print(f"{len(ql.calls)=}")
    for sql, calls in sorted(categorized_calls.items(), reverse=True, key=lambda c: len(c[1])):
        print(f"{len(calls)=}: {sql=}")
