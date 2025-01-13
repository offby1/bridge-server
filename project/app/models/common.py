from __future__ import annotations

import bridge.seat

# {1: 'NORTH', 2: 'EAST', 3: 'SOUTH', 4: 'WEST'}
SEAT_CHOICES: dict[int, str] = {v.value: v.name for v in bridge.seat.Seat.__members__.values()}
LETTER_SEAT_CHOICES: dict[str, str] = {"N": "NORTH", "E": "EAST", "S": "SOUTH", "W": "WEST"}
