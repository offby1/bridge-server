import bridge.seat

# {1: 'NORTH', 2: 'EAST', 3: 'SOUTH', 4: 'WEST'}
SEAT_CHOICES = {v.value: k for k, v in bridge.seat.Seat.__members__.items()}


from .board import Board  # noqa
from .message import Message  # noqa
from .player import (  # noqa
    PartnerException,
    Player,
    PlayerException,
)
from .seat import Seat  # noqa
from .table import Table  # noqa
