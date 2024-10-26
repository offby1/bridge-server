from __future__ import annotations

import bridge.seat

# {1: 'NORTH', 2: 'EAST', 3: 'SOUTH', 4: 'WEST'}
SEAT_CHOICES: dict[int, str] = {v.value: v.name for v in bridge.seat.Seat.__members__.values()}
