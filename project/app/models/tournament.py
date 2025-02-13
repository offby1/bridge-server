from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib import admin
from django.core.signals import request_started
from django.db import models, transaction
from django.dispatch import receiver
from django.utils import timezone

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from app.models import Player, Table


logger = logging.getLogger(__name__)


@receiver(request_started)
def check_for_expirations(sender, **kwargs) -> None:
    logger.debug(f"{sender=} {kwargs=}: {Tournament.objects.count()} tournaments")

    t: Tournament
    with transaction.atomic():
        for t in Tournament.objects.filter(is_complete=False).filter(
            models.Q(signup_deadline__isnull=False)
            | models.Q(play_completion_deadline__isnull=False)
        ):
            logger.debug("Checking %s: ", t)
            logger.debug(
                "signup deadline %s %s passed",
                t.signup_deadline,
                "has" if t.signup_deadline_has_passed() else "has not",
            )
            logger.debug(
                "play completion deadline %s %s passed",
                t.play_completion_deadline,
                "has" if t.play_completion_deadline_has_passed() else "has not",
            )
            if t.play_completion_deadline_has_passed():
                t.maybe_complete()
                logger.warning("Ejecting players")

                from app.models import Hand

                hands = Hand.objects.filter(table__in=t.table_set.all())
                for h in hands:
                    if h.is_complete:
                        continue
                    if h.is_abandoned:
                        continue
                    for s in h.table.seats:
                        s.player.unseat_me()
                        s.player.save()
                t.is_complete = True
                t.save()
                continue

            if t.signup_deadline_has_passed():
                # TODO -- come up with an appropriate movement, and assign it to this tournament.
                logger.warning(
                    "Tournament #%s's signup deadline has passed; imagine I came up with a movement for %d tables",
                    t.display_number,
                    t.table_set.count(),
                )
                logger.warning(
                    "Alas, I already pre-created %d boards, which probably isn't the right number.",
                    t.board_set.count(),
                )


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
            if ("display_number") not in kwargs:
                kwargs["display_number"] = self.count() + 1

            now = timezone.now()
            kwargs.setdefault("signup_deadline", now + datetime.timedelta(seconds=300))
            kwargs.setdefault(
                "play_completion_deadline",
                kwargs["signup_deadline"] + datetime.timedelta(seconds=300),
            )

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
                Board.objects.create_from_attributes(attributes=board_attributes, tournament=t)
            logger.debug("Created new tournament with %s", t.board_set.all())
            return t

    def current(self) -> Tournament | None:
        return self.filter(is_complete=False).first()

    def running(self) -> models.QuerySet:
        return self.filter(Tournament.between_deadlines_Q())

    def get_or_create_running_tournament(self) -> tuple[Tournament, bool]:
        with transaction.atomic():
            incomplete_qs = self.filter(is_complete=False)

            if not incomplete_qs.exists():
                return self.create(), True

            first_incomplete = incomplete_qs.first()
            assert first_incomplete is not None
            first_incomplete.maybe_complete()

            if first_incomplete.is_complete:
                logger.warning(
                    "OK, that's surprising; %s was incomplete but now I just completed it?",
                    first_incomplete,
                )
                return self.create(), True

            logger.debug(
                f"An incomplete tournament (#{first_incomplete.display_number}) already exists; no need to create a new one",
            )
            return first_incomplete, False


# This might actually be a "session" as per https://en.wikipedia.org/wiki/Duplicate_bridge#Pairs_game
class Tournament(models.Model):
    if TYPE_CHECKING:
        from app.models.board import Board

        board_set = RelatedManager["Board"]()
        table_set = RelatedManager[Table]()

    is_complete = models.BooleanField(default=False)
    display_number = models.SmallIntegerField(unique=True)

    signup_deadline = models.DateTimeField(
        null=True, default=None, db_comment="NULL means 'infintely far in the future'"
    )  # type: ignore[call-overload]
    play_completion_deadline = models.DateTimeField(
        null=True, default=None, db_comment="NULL means 'infintely far in the future'"
    )  # type: ignore[call-overload]

    objects = TournamentManager()

    def signup_deadline_has_passed(self) -> bool:
        if self.signup_deadline is None:
            return False
        return timezone.now() > self.signup_deadline

    def play_completion_deadline_has_passed(self) -> bool:
        if self.play_completion_deadline is None:
            return False
        return timezone.now() > self.play_completion_deadline

    @staticmethod
    def between_deadlines_Q() -> models.Q:
        now = timezone.now()
        return models.Q(signup_deadline__lte=now) & models.Q(play_completion_deadline__gte=now)

    def is_running(self) -> bool:
        if self.is_complete:
            return False

        if self.play_completion_deadline is None:
            return True

        assert self.signup_deadline is not None

        return Tournament.objects.filter(pk=self.pk).filter(self.between_deadlines_Q()).exists()

    def __str__(self) -> str:
        status = (
            "completed"
            if self.is_complete
            else "currently_running"
            if self.is_running()
            else "expired"
        )
        return f"tournament #{self.display_number}; {status}; {self.board_set.count()} boards"

    def hands(self) -> models.QuerySet:
        from app.models import Hand

        rv = Hand.objects.filter(board__in=self.board_set.all()).distinct()
        logger.debug("%s has %d hands", self, rv.count())
        return rv

    def tables(self) -> models.QuerySet:
        from app.models import Table

        rv = Table.objects.filter(hand__in=self.hands()).distinct()
        logger.debug("%s has %d tables", self, rv.count())
        return rv

    def maybe_complete(self) -> None:
        with transaction.atomic():
            if self.is_complete:
                logger.info("Pff, no need to complete %s since it's already complete.", self)
                return

            num_hands_needed_for_completion = self.tables().count() * self.board_set.count()

            if num_hands_needed_for_completion == 0:
                logger.info(
                    "We don't consider %s to be complete because it's never had any tables assigned.",
                    self,
                )
                return

            complete_hands = [h for h in self.hands() if h.is_complete]

            if len(complete_hands) == num_hands_needed_for_completion:
                explanation = f"We've played {num_hands_needed_for_completion=}, so we're done"
                logger.debug(explanation)
                self.is_complete = True
                self.save()
                self.eject_all_pairs(explanation=explanation)
                logger.debug(
                    f"Marked myself %s as complete, and ejected all pairs from {self.tables()}",
                    self,
                )
                return

            logger.debug(
                f"{len(complete_hands)=}, which is not == {num_hands_needed_for_completion=} ({self.tables().count()=} * {self.board_set.count()=}), so we're not done"
            )

    def eject_all_pairs(self, explanation: str) -> None:
        logger.debug(
            f"{explanation=}; I should go around ejecting partnerships from tables.",
        )
        with transaction.atomic():
            for t in self.tables():
                for seat in t.seat_set.all():
                    p: Player = seat.player

                    message = f"{p} is now in the lobby"
                    p.unseat_me()
                    p.save()

                    if not p.synthetic:
                        message += ", and unbottified"
                    logger.debug("%s", message)

                # oddly, `t.current_hand.save()` seems to have no effect; hence the temp variable `h`
                h = t.current_hand
                h.abandoned_because = explanation
                h.save()

    def _check_no_more_than_one_running_tournament(self) -> None:
        if not self.is_running():
            return

        if Tournament.objects.running().exclude(pk=self.pk).exists():
            msg = "Cannot save incomplete tournament %s when you've already got one going, Mrs Mulwray"
            raise Exception(msg, self)

    def save(self, *args, **kwargs) -> None:
        self._check_no_more_than_one_running_tournament()
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.CheckConstraint(  # type: ignore[call-arg]
                name="%(app_label)s_%(class)s_cant_have_just_one_deadline",
                condition=(
                    (
                        models.Q(signup_deadline__isnull=True)
                        & models.Q(play_completion_deadline__isnull=True)
                    )
                    | models.Q(signup_deadline__isnull=False)
                    & models.Q(play_completion_deadline__isnull=False)
                ),
            ),
            models.CheckConstraint(  # type: ignore[call-arg]
                name="%(app_label)s_%(class)s_play_deadline_must_follow_signup_deadline",
                condition=(
                    (
                        models.Q(signup_deadline__isnull=True)
                        & models.Q(play_completion_deadline__isnull=True)
                    )
                    | models.Q(play_completion_deadline__gt=models.F("signup_deadline"))
                ),
            ),
        ]


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ["display_number", "signup_deadline", "play_completion_deadline"]
