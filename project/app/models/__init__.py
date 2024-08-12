import bridge.seat

SEAT_CHOICES = {v.value: k for k, v in bridge.seat.Seat.__members__.items()}


from .player import PartnerException, Player, PlayerException  # noqa
from .seat import Seat  # noqa
from .table import Table  # noqa
