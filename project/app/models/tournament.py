from __future__ import annotations

import datetime
import inspect
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


# TODO -- look at the arguments, and do nothing if the URL requested is irrelevant.  Specifically, it might be
# "/metrics" once we've wired up Prometheus.  Prometheus GETs /metrics every second, and we don't need to poke the DB
# every second.
@receiver(request_started)
def check_for_expirations(sender, **kwargs) -> None:
    t: Tournament
    with transaction.atomic():
        incompletes = Tournament.objects.filter(is_complete=False)

        logger.debug(f"{Tournament.objects.count()} tournaments: {incompletes=}")

        for t in incompletes:
            t.maybe_complete()
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
                logger.warning("Ejecting players")

                t.is_complete = True
                t.save()
                t.eject_all_pairs(
                    explanation=f"Tournament's play deadline {t.play_completion_deadline} has passed"
                )
                logger.debug(
                    "Marked myself %s as complete, and ejected all pairs from %s",
                    t,
                    t.tables(),
                )
                continue

            if t.signup_deadline_has_passed():
                # TODO -- come up with an appropriate movement, and assign it to this tournament.
                logger.debug("%s might need some boards; who knows?", t)
                logger.warning(
                    "Alas, I already pre-created %d boards, which probably isn't the right number.",
                    t.board_set.count(),
                )
                table: Table
                for table in t.table_set.all():
                    if not table.hand_set.exists():
                        logger.debug("%s of %s needs a board!", table, t)
                        t.add_boards(n=2)
                        table.next_board()


class TournamentStatus:
    pass


class Complete(TournamentStatus):
    pass


class Running(TournamentStatus):
    pass


class OpenForSignup(TournamentStatus):
    pass


def _status(
    *,
    is_complete: bool,
    signup_deadline: datetime.datetime | None,
    play_completion_deadline: datetime.datetime | None,
    as_of: datetime.datetime,
) -> type[TournamentStatus]:
    if is_complete:
        return Complete
    if signup_deadline is None:
        return Running
    assert play_completion_deadline is not None
    if as_of < signup_deadline:
        return OpenForSignup
    if as_of > play_completion_deadline:
        logger.warning(
            "Some tournament's play_completion_deadline has passed, but it hasn't (yet) been marked is_complete"
        )
        return Complete
    return Running


class TournamentManager(models.Manager):
    def create(self, *args, **kwargs) -> Tournament:
        kwargs = kwargs.copy()
        with transaction.atomic():
            if ("display_number") not in kwargs:
                kwargs["display_number"] = self.count() + 1

            now = timezone.now()
            kwargs.setdefault("signup_deadline", now + datetime.timedelta(seconds=300))
            kwargs.setdefault(
                "play_completion_deadline",
                kwargs["signup_deadline"] + datetime.timedelta(seconds=300),
            )

            rv: Tournament = super().create(*args, **kwargs)
            for fi in inspect.stack()[0:3]:
                logger.debug(f"-- {fi.function} {fi.filename} {fi.lineno}")
            logger.debug("Just created %s", rv)
            logger.debug(
                "Now it's %s; signup_deadline is %s; play_completion_deadline is %s",
                now,
                rv.signup_deadline,
                rv.play_completion_deadline,
            )
            return rv

    def current(self) -> Tournament | None:
        return self.filter(is_complete=False).first()

    def running(self) -> models.QuerySet:
        return self.filter(Tournament.between_deadlines_Q())

    def get_or_create_tournament_open_for_signups(self) -> tuple[Tournament, bool]:
        from app.models.board import BOARDS_PER_TOURNAMENT

        with transaction.atomic():
            a_few_seconds_from_now = timezone.now() + datetime.timedelta(seconds=10)
            incomplete_qs = self.filter(is_complete=False).filter(
                models.Q(signup_deadline__gte=a_few_seconds_from_now)
                | models.Q(signup_deadline__isnull=True)
            )
            logger.debug(f"{a_few_seconds_from_now=} {incomplete_qs=}")
            if not incomplete_qs.exists():
                logger.debug("No incomplete tournament exists, so we will create a new one")
                new_tournament = self.create()
                logger.debug("... namely %s", new_tournament)
                return new_tournament, True

            first_incomplete: Tournament | None = incomplete_qs.first()
            logger.debug(
                "An incomplete tournament (%s) exists, so we didn't need to create a new one",
                first_incomplete,
            )

            assert first_incomplete is not None
            first_incomplete.maybe_complete()

            if first_incomplete.is_complete:
                new_tournament = self.create()
                logger.debug(
                    "%s was incomplete but now I just completed it; created a new empty tournament %s",
                    first_incomplete.short_string(),
                    new_tournament.short_string(),
                )
                return new_tournament, True

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

    def add_boards(self, *, n: int) -> None:
        from app.models.board import (
            Board,
            board_attributes_from_display_number,
        )

        with transaction.atomic():
            assert (
                not self.board_set.exists()
            ), f"Don't add boards to {self}; it already has {self.board_set.count()}!!"
            assert (
                not self.is_complete
            ), f"Wassup! Don't add boards to a completed tournament!! {self}"

            for display_number in range(1, n + 1):
                board_attributes = board_attributes_from_display_number(
                    display_number=display_number,
                    rng_seeds=[
                        str(display_number).encode(),
                        str(self.pk).encode(),
                        settings.SECRET_KEY.encode(),
                    ],
                )
                Board.objects.create_from_attributes(attributes=board_attributes, tournament=self)
            logger.debug("Added %d boards to %s", self.board_set.count(), self)

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
        return self.status() is Running

    def status(self) -> type[TournamentStatus]:
        return _status(
            is_complete=self.is_complete,
            signup_deadline=self.signup_deadline,
            play_completion_deadline=self.play_completion_deadline,
            as_of=timezone.now(),
        )

    def short_string(self) -> str:
        return f"tournament #{self.display_number}"

    def __str__(self) -> str:
        rv = f"{self.short_string()}; {self.status().__name__}"
        if self.status() is not Complete:
            num_completed = sum([h.is_complete for h in self.hands()])
            rv += f"; {num_completed} hands played out of {self.board_set.count() * self.table_set.count()}"

        return rv

    def hands(self) -> models.QuerySet:
        from app.models import Hand

        return Hand.objects.filter(board__in=self.board_set.all()).distinct()

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
                explanation = f"{self.short_string()} has played {num_hands_needed_for_completion} hands, so it is completed"
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
