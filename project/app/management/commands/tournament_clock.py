"""Honour tournament deadlines.

Signups close and play completes at wall-clock times, so something has to be watching
the clock. That used to be a `request_finished` signal receiver, which meant deadlines
were honoured only as often as somebody sent an HTTP request; see
`app.models.tournament.advance_expired_tournaments` for why that was worse than it
sounds.

The game does not advance without this process running.
"""

from __future__ import annotations

import logging
import time

from app.models.tournament import advance_expired_tournaments
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Watch for tournament deadlines and honour them.  Runs until killed."

    def handle(self, *_args, **_options) -> None:
        logger.info("Tournament clock starting")

        while True:
            wake_at = advance_expired_tournaments()
            seconds = max(0.0, (wake_at - timezone.now()).total_seconds())
            logger.info("Next deadline at %s; sleeping %.1fs", wake_at.isoformat(), seconds)
            time.sleep(seconds)
