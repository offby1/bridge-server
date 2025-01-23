from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models, transaction

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from app.models import Player


logger = logging.getLogger(__name__)


class TournamentManager(models.Manager):
    # When should we call this?
    # Whenever there are no more unplayed boards.
    def create(self, *args, **kwargs) -> Tournament:
        from app.models.board import (
            BOARDS_PER_TOURNAMENT,
            Board,
            board_attributes_from_display_number,
        )

        with transaction.atomic():
            t = super().create(*args, **kwargs)
            # create all the boards ahead of time.
            for display_number in range(1, BOARDS_PER_TOURNAMENT + 1):
                board_attributes = board_attributes_from_display_number(
                    display_number=display_number,
                    rng_seeds=[
                        str(display_number).encode(),
                        str(t.pk).encode(),
                        settings.SECRET_KEY.encode(),
                    ],
                )
                Board.objects.create_from_attributes(
                    attributes=board_attributes, tournament=t
                )
            logger.debug("Created new tournament with %s", t.board_set.all())
            return t

    def maybe_new_tournament(self) -> Tournament | None:
        with transaction.atomic():
            currently_running = self.filter(is_complete=False).first()
            if currently_running is not None:
                currently_running.maybe_complete()
                if not currently_running.is_complete:
                    logger.debug(
                        "An incomplete tournament already exists; no need to create a new one",
                    )
                    return None
            return self.create()


# This might actually be a "session" as per https://en.wikipedia.org/wiki/Duplicate_bridge#Pairs_game
class Tournament(models.Model):
    if TYPE_CHECKING:
        from app.models.board import Board

        board_set = RelatedManager["Board"]()

    is_complete = models.BooleanField(default=False)

    objects = TournamentManager()

    def __str__(self) -> str:
        return f"tournament {self.pk}"

    def hands(self) -> models.QuerySet:
        from app.models import Hand

        return Hand.objects.filter(board__in=self.board_set.all()).distinct()

    def tables(self) -> models.QuerySet:
        from app.models import Table

        return Table.objects.filter(hand__in=self.hands()).distinct()

    def maybe_complete(self) -> None:
        with transaction.atomic():
            if self.is_complete:
                logger.info(
                    "Pff, no need to complete %s since it's already complete.", self
                )
                return

            num_needed_for_completion = self.tables().count() * self.board_set.count()
            complete_hands = [h for h in self.hands() if h.is_complete]

            if len(complete_hands) == num_needed_for_completion:
                logger.debug(
                    f"{len(complete_hands)=}, which is == {num_needed_for_completion=} ({self.tables().count()=} * {self.board_set.count()=}), so we're done"
                )
                self.is_complete = True
                self.save()
                self.eject_all_pairs()
                logger.debug(
                    "Marked myself %s as complete, and ejected all pairs from tables",
                    self,
                )
                return

            logger.debug(
                f"{len(complete_hands)=}, which is not == {num_needed_for_completion=} ({self.tables().count()=} * {self.board_set.count()=}), so we're not done"
            )

    def eject_all_pairs(self) -> None:
        logger.debug(
            "Since I just completed, I should go around ejecting partnerships from tables.",
        )
        with transaction.atomic():
            for t in self.tables():
                for seat in t.seat_set.all():
                    p: Player = seat.player

                    p.currently_seated = False
                    p.save()
                    p.toggle_bot(False)
                    logger.debug("%s is now in the lobby, and un-bottified", p)

    def _check_no_more_than_one_running_tournament(self) -> None:
        if self.is_complete:
            return

        if Tournament.objects.filter(is_complete=False).exists():
            msg = "Cannot save incomplete tournament %s when you've already got one going, Mrs Mulwray"
            raise Exception(msg, self)

    def save(self, *args, **kwargs) -> None:
        self._check_no_more_than_one_running_tournament()
        super().save(*args, **kwargs)
