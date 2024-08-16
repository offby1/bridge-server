import bridge.seat

SEAT_CHOICES = {v.value: k for k, v in bridge.seat.Seat.__members__.items()}


from .message import Message  # noqa
from .player import (  # noqa
    PartnerException,
    Player,
    PlayerException,
)
from .seat import Seat  # noqa
from .table import Table  # noqa
