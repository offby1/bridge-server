from __future__ import annotations

import bridge.seat

# {"N": "NORTH", "E": "EAST", "S": "SOUTH", "W": "WEST"}
SEAT_CHOICES: dict[str, str] = {v.value: v.name for v in bridge.seat.Seat.__members__.values()}
attribute_names = [s.name for s in bridge.seat.Seat]
