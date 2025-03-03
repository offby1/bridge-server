from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from django.contrib import admin
from django.core.signals import request_started
from django.db import models, transaction
from django.dispatch import receiver
from django.utils import timezone

from app.models.signups import TournamentSignup
from app.models.throttle import throttle
import app.utils.movements


if TYPE_CHECKING:
    from collections.abc import Sequence
    from django.db.models.manager import RelatedManager

    from app.models import Player, Table


logger = logging.getLogger(__name__)


class TournamentSignupError(Exception):
    pass


class PlayerNotSeatedError(TournamentSignupError):
    pass


class PlayerNeedsPartnerError(TournamentSignupError):
    pass


class NotOpenForSignupError(TournamentSignupError):
    pass


def _do_signup_expired_stuff(tour: "Tournament") -> None:
    p: Player
    with transaction.atomic():
        if tour.board_set.exists():
            logger.debug("%s looks like it's had boards assigned already; bailing", tour)
            return

        # It expired without any signups -- just nuke it
        if not tour.signed_up_pairs():
            logger.warning("%s has no signups; deleting it", tour)
            tour.delete()
            return

        # Now seat everyone who's signed up, plus a pair of synths, if needed.
        # TODO -- consult the movement to see whom to seat where.
        # and then TODO -- keep doing that as the movement's "rounds" progress.

        for _ in range(2):
            signed_up_pairs = tour.signed_up_pairs()

            if len(signed_up_pairs) % 2 == 0:
                break

            from app.models import Player

            p2 = Player.objects.create_synthetic()
            p2.partner = Player.objects.create_synthetic()
            p2.partner.partner = p2
            p2.partner.save()
            p2.save()

            for p in (p2, p2.partner):
                TournamentSignup.objects.create(tournament=tour, player=p)

            logger.debug("Created synths %s and %s for %s", p2, p2.partner, tour)

        assert len(signed_up_pairs) % 2 == 0
        logger.debug("%d pairs are waiting", len(signed_up_pairs))

        movement = tour.get_movement()

        # This creates tables, and seats players.
        movement.start_round(round_number=0, tournament=tour)


# TODO -- replace this with a scheduled solution -- see the "django-q2" branch
@receiver(request_started)
@throttle(seconds=60)
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
                t.is_complete = True
                t.save()
                continue

            if t.signup_deadline_has_passed():
                _do_signup_expired_stuff(t)


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
                max_ = self.aggregate(models.Max("display_number"))["display_number__max"] or 0
                kwargs["display_number"] = max_ + 1

            now = timezone.now()
            kwargs.setdefault("signup_deadline", now + datetime.timedelta(seconds=300))
            kwargs.setdefault(
                "play_completion_deadline",
                kwargs["signup_deadline"] + datetime.timedelta(seconds=300),
            )

            rv: Tournament = super().create(*args, **kwargs)
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

    def open_for_signups(self) -> models.QuerySet:
        return self.filter(is_complete=False).filter(signup_deadline__gte=timezone.now())

    def get_or_create_tournament_open_for_signups(self) -> tuple[Tournament, bool]:
        with transaction.atomic():
            a_few_seconds_from_now = timezone.now() + datetime.timedelta(seconds=10)
            incomplete_and_open_tournaments_qs = self.filter(is_complete=False).filter(
                models.Q(signup_deadline__gte=a_few_seconds_from_now)
            )
            logger.debug(f"{a_few_seconds_from_now=} {incomplete_and_open_tournaments_qs=}")
            if not incomplete_and_open_tournaments_qs.exists():
                logger.debug(
                    "No tournament exists that is incomplete, and open for signup through %s, so we will create a new one",
                    a_few_seconds_from_now,
                )
                new_tournament = self.create()
                logger.debug("... namely %s", new_tournament)
                return new_tournament, True

            first_incomplete: Tournament | None = incomplete_and_open_tournaments_qs.order_by(
                "signup_deadline"
            ).first()
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
        null=True, blank=True, default=None, db_comment="NULL means 'infintely far in the future'"
    )  # type: ignore[call-overload]
    play_completion_deadline = models.DateTimeField(
        null=True, blank=True, default=None, db_comment="NULL means 'infintely far in the future'"
    )  # type: ignore[call-overload]

    objects = TournamentManager()

    def what_round_is_it(self) -> int:
        num_hands = self.hands().count()
        mvmt = self.get_movement()
        num_tables = len(mvmt.table_settings_by_table_number)
        wat = num_hands // (num_tables * mvmt.boards_per_round)
        logger.debug(
            "Well, here's how many hands have been played: %d; I guess that means %d",
            num_hands,
            wat,
        )
        return 0

    def signed_up_pairs(self) -> Sequence[app.utils.movements.Pair]:
        signed_up_players = set()
        rv = []

        for su in TournamentSignup.objects.filter(tournament=self).all():
            p = su.player

            assert p is not None

            if p.partner is None:
                logger.debug("Not pairing up %s because they have no partner", p.name)
                continue

            if p.currently_seated:
                logger.debug("Not pairing up %s because they are already seated", p.name)
                continue

            if p.pk not in signed_up_players and p.partner.pk not in signed_up_players:
                rv.append(
                    app.utils.movements.Pair(
                        id=frozenset([p.pk, p.partner.pk]), names=f"{p.name}, {p.partner.name}"
                    )
                )
                signed_up_players.add(p.pk)
                signed_up_players.add(p.partner.pk)

        return rv

    def unplayed_boards_for(self, *, table: Table) -> models.QuerySet:
        from app.models import Board

        played_boards = self.board_set.all()
        what_round_is_it = self.what_round_is_it()
        logger.debug(
            "%s have been played at %s; imagine %d really was the number of completed rounds, and therefore I knew which boards for this round had *not* been played.",
            ", ".join([f"b#{b.display_number}" for b in played_boards]),
            table,
            what_round_is_it,
        )
        return Board.objects.none()

    def next_movement_round(self) -> None:
        if self.is_complete:
            logger.info("%s is complete; no next round for you", self)
        else:
            logger.debug(
                f"Imagine I checked all my tables ({self.table_set.all()}), and if they were all complete, destroying them and creating new ones"
            )

    def get_movement(self) -> app.utils.movements.Movement:
        boards_per_round = 3  # arbitrary
        logger.debug(f"{self.signed_up_pairs()=}")
        return app.utils.movements.Movement.from_pairs(
            boards_per_round=boards_per_round, pairs=self.signed_up_pairs(), tournament=self
        )

    def signup_deadline_has_passed(self) -> bool:
        if self.signup_deadline is None:
            return False
        return timezone.now() > self.signup_deadline

    def play_completion_deadline_has_passed(self) -> bool:
        if self.play_completion_deadline is None:
            return False
        return timezone.now() > self.play_completion_deadline

    def is_running(self) -> bool:
        return self.status() is Running

    def status(self) -> type[TournamentStatus]:
        return _status(
            is_complete=self.is_complete,
            signup_deadline=self.signup_deadline,
            play_completion_deadline=self.play_completion_deadline,
            as_of=timezone.now(),
        )

    def status_str(self) -> str:
        return self.status().__name__

    def short_string(self) -> str:
        return f"tournament #{self.display_number}"

    def sign_up(self, player: Player) -> None:
        if self.status() is not OpenForSignup:
            msg = f"Tournament #{self.display_number} is {self.status_str()}, not open for signup; the signup deadline was {self.signup_deadline}"
            raise NotOpenForSignupError(msg)
        if player.partner is None:
            raise PlayerNeedsPartnerError(f"{player.name} has no partner")
        if any(p.currently_seated for p in (player, player.partner)):
            raise PlayerNotSeatedError(
                f"At least one of {(player, player.partner)} is currently seated"
            )
        for p in (player, player.partner):
            TournamentSignup.objects.get_or_create(tournament=self, player=p)
            logger.debug("Just signed %s up for tournament #%s", p.name, self.display_number)

    def signed_up_players(self) -> models.QuerySet:
        from app.models import Player

        return Player.objects.filter(
            player__in=TournamentSignup.objects.filter(tournament=self).values_list(
                "player", flat=True
            )
        )

    def __repr__(self) -> str:
        return f"<Tournament #{self.display_number} pk={self.pk}>"

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

                return

            logger.debug(
                f"{len(complete_hands)=}, which is not == {num_hands_needed_for_completion=} ({self.tables().count()=} * {self.board_set.count()=}), so we're not done"
            )

    def _eject_all_pairs(self, explanation: str) -> None:
        logger.debug(
            f"{explanation=}; ejecting partnerships from tables.",
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

    def save(self, *args, **kwargs) -> None:
        if self.is_complete:
            TournamentSignup.objects.filter(tournament=self).delete()
            self._eject_all_pairs(
                # TODO -- distinguish between "all the boards have been played" vs "was aborted because the play
                # completion deadline passed"
                explanation=f"Tournament is complete; maybe its play deadline {self.play_completion_deadline} has passed"
            )
            logger.debug(
                "Marked myself %s as complete, and ejected all pairs from %s",
                self,
                self.tables(),
            )
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
    list_display = ["display_number", "is_complete", "signup_deadline", "play_completion_deadline"]
