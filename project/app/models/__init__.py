from __future__ import annotations

import collections
import contextlib

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
        self.calls = []

    def __call__(self, execute, sql, params, many, context):
        self.calls.append((sql, params, many, context))
        return execute(sql, params, many, context)


@contextlib.contextmanager
def logged_queries(name=None):
    ql = QueryLogger(name=name)
    with connection.execute_wrapper(ql):
        try:
            yield ql
        finally:
            categorized_calls = collections.defaultdict(list)
            for call in ql.calls:
                sql, params, many, context = call
                categorized_calls[sql].append(call)
            print(f"{len(ql.calls)=}")
            for sql, calls in sorted(
                categorized_calls.items(), reverse=True, key=lambda c: len(c[1])
            ):
                if "SAVEPOINT" in sql:  # bo-ring!
                    continue
                if "django_eventstream" in sql:  # also boring
                    continue
                print(f"{len(calls)=}: {sql:.100}")
                params = str(collections.Counter([c[1] for c in calls]))[0:100]
                print(f"   ... {params}")
