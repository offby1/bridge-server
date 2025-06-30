from __future__ import annotations

import datetime
import logging
import operator
from typing import TYPE_CHECKING, Literal

from django.contrib import admin
from django.core.cache import cache
from django.core.signals import request_finished
from django.db import models, transaction
from django.dispatch import receiver
from django.utils import timezone


from bridge.xscript import BrokenDownScore

import app.models
import app.models.common
from app.models.signups import TournamentSignup
from app.models.throttle import throttle
from app.models.types import PK
from app.models.utils import assert_type
import app.utils.movements
import app.utils.scoring

if TYPE_CHECKING:
    from collections.abc import Generator
    from django.db.models.manager import RelatedManager

    from app.models import Hand, Player


logger = logging.getLogger(__name__)


class TournamentSignupError(Exception):
    pass


class PlayerNotSeatedError(TournamentSignupError):
    pass


class PlayerNeedsPartnerError(TournamentSignupError):
    pass


class NotOpenForSignupError(TournamentSignupError):
    pass


class NoPairs(Exception):
    pass


WAY_DISTANT_PLAY_COMPLETION_DEADLINE = datetime.datetime.max.replace(tzinfo=datetime.UTC)


def _do_signup_expired_stuff(tour: "Tournament") -> None:
    with transaction.atomic():
        if tour.hands().exists():
            logger.debug("'%s' looks like it has hands already; bailing", tour)
            return

        # It expired without any signups -- just nuke it
        if not TournamentSignup.objects.filter(tournament=tour).exists():
            logger.warning("'%s' has no signups; deleting it", tour)
            tour.delete()
            return

        TournamentSignup.objects.create_synths_for(tour)
        tour.create_hands_for_round(zb_round_number=0)
        assert tour.hands().count() == tour.get_movement().num_rounds

        if tour.play_completion_deadline == WAY_DISTANT_PLAY_COMPLETION_DEADLINE:
            tour.play_completion_deadline = tour.compute_play_completion_deadline()
            tour.save()


# TODO -- replace this with a scheduled solution -- see the "django-q2" branch
# Now that I think about it, this could also be a middleware
@receiver(request_finished)
@throttle(seconds=60)
def check_for_expirations(sender, **kwargs) -> None:
    t: Tournament

    with transaction.atomic():
        incompletes = Tournament.objects.incompletes().filter(signup_deadline__isnull=False)

        for t in incompletes:
            if t.play_completion_deadline_has_passed():
                t.completed_at = t.play_completion_deadline
                deadline_str = t.play_completion_deadline.isoformat()
                t.abandon_all_hands(reason=f"Play completion deadline ({deadline_str}) has passed")
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


# Hopefully our tournament won't be in the state for more than a millisecond
class ComputingPlayCompletionDeadline(TournamentStatus):
    pass


class TournamentManager(models.Manager):
    def create(self, *args, **kwargs) -> Tournament:
        kwargs = kwargs.copy()
        with transaction.atomic():
            if ("display_number") not in kwargs:
                max_ = self.aggregate(models.Max("display_number"))["display_number__max"] or 0
                kwargs["display_number"] = max_ + 1

            now = timezone.now()
            kwargs.setdefault("signup_deadline", now + datetime.timedelta(seconds=300))

            if "play_completion_deadline" in kwargs:
                import os

                assert os.environ.get("PYTEST_VERSION") is not None, (
                    "Uh oh, some non-test code is trying to set the play_completion_deadline on a new tournament"
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

    def open_for_signups(self) -> models.QuerySet:
        return self.incompletes().filter(signup_deadline__gte=timezone.now())

    def get_or_create_tournament_open_for_signups(
        self, **creation_kwargs
    ) -> tuple[Tournament, bool]:
        with transaction.atomic():
            now = timezone.now()
            incomplete_and_open_tournaments_qs = self.incompletes().filter(
                models.Q(signup_deadline__gte=now)
            )

            logger.debug(f"{now=} {incomplete_and_open_tournaments_qs=}")
            if not incomplete_and_open_tournaments_qs.exists():
                logger.debug(
                    "No tournament exists that is incomplete, and open for signup through %s, so we will create a new one",
                    now,
                )
                new_tournament = self.create(**creation_kwargs)
                logger.debug("... namely '%s'", new_tournament)
                return new_tournament, True

            first_incomplete: Tournament | None = incomplete_and_open_tournaments_qs.order_by(
                "signup_deadline"
            ).first()
            logger.debug(
                "An incomplete tournament (%s) exists, so we didn't need to create a new one",
                first_incomplete,
            )

            assert first_incomplete is not None

            logger.debug(
                f"An incomplete tournament (#{first_incomplete.display_number}) already exists; no need to create a new one",
            )
            return first_incomplete, False

    def incompletes(self) -> models.QuerySet:
        return self.filter(completed_at__isnull=True)


class Tournament(models.Model):
    if TYPE_CHECKING:
        from app.models.board import Board

        board_set = RelatedManager["Board"]()

    boards_per_round_per_table = models.PositiveSmallIntegerField(default=3)

    completed_at = models.DateTimeField(null=True)

    display_number = models.SmallIntegerField(unique=True)

    signup_deadline = models.DateTimeField()
    play_completion_deadline = models.DateTimeField(
        default=WAY_DISTANT_PLAY_COMPLETION_DEADLINE,
        db_comment='"a billion years from now" means we don\'t yet know how many players we have, hence cannot compute a movement',
    )  # type: ignore[call-overload]

    tempo_seconds = models.FloatField(
        db_comment="Time, in seconds, that the bot will wait before making a call or play",
        default=1.0,
    )

    objects = TournamentManager()

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    def matchpoints_by_pair(self) -> dict[tuple[str, str], tuple[int, float]]:
        # Convert the final score, which might be zero, into a dict of kwargs
        def consistent_score(fs: BrokenDownScore | Literal[0]) -> dict[str, int]:
            if fs == 0:
                return {"ns_raw_score": 0, "ew_raw_score": 0}
            return {"ns_raw_score": fs.north_south_points, "ew_raw_score": fs.east_west_points}

        hands = (
            app.utils.scoring.Hand(
                ns_id=(h.North, h.South),
                ew_id=(h.East, h.West),
                board_id=h.board.pk,
                **consistent_score(h.get_xscript().final_score()),
            )
            for h in self.hands()
            .filter(abandoned_because__isnull=True)
            .select_related(*app.models.common.attribute_names)
            .select_related("board")
            .select_related(*[f"{d}__user" for d in app.models.common.attribute_names])
        )

        scorer = app.utils.scoring.Scorer(hands=list(hands))
        return {
            (k[0].as_link(), k[1].as_link()): v for k, v in scorer.matchpoints_by_pairs().items()
        }

    def players(self) -> models.QuerySet:
        hands = self.hands()
        expression = models.Q(pk__in=hands.values("North"))
        expression |= models.Q(pk__in=hands.values("East"))
        expression |= models.Q(pk__in=hands.values("South"))
        expression |= models.Q(pk__in=hands.values("West"))
        return app.models.Player.objects.filter(expression).distinct()

    def compute_play_completion_deadline(self) -> datetime.datetime:
        # Compute the play deadline from

        # - the signup deadline

        # - 7.5 minutes per hand (https://web2.acbl.org/documentlibrary/clubs/cdHandbook.pdf says "The guideline for
        # - ACBL events is 15 minutes per two boards.")

        # - the number of boards any individual will play -- namely, the number of rounds times the number of boards per
        # - round.

        mvmt = self.get_movement()
        return (
            self.signup_deadline
            + mvmt.num_rounds
            * mvmt.boards_per_round_per_table
            * datetime.timedelta(seconds=450)  # 7.5 minutes
        )

    def check_consistency(self) -> None:
        """
        See if we have all the boards called for by our movement.
        This might not be the case if we were created from an old json Django fixture.
        """
        mvmt = self.get_movement()
        expected = mvmt.boards_per_round_per_table * len(mvmt.table_settings_by_zb_table_number)
        assert self.board_set.count() == expected, (
            f"Expected {mvmt.boards_per_round_per_table=} * {len(mvmt.table_settings_by_zb_table_number)=} => {expected} boards, but got {self.board_set.count()}"
        )

        for b in self.board_set.all():
            assert b.group is not None, f"Hey! {b=} ain't got no group"

    def the_round_just_ended(self) -> int | None:
        num_completed_rounds, num_hands_this_round = self.rounds_played()
        if num_completed_rounds > 0 and num_hands_this_round == 0:
            return num_completed_rounds
        return None

    def rounds_played(self) -> tuple[int, int]:
        """
        Returns a tuple: the number of *completed* rounds, and the number of :model:`app.hand` s played in the current round.
        """
        num_completed_hands = self.hands().filter(is_complete=True).count()
        mvmt = self.get_movement()
        num_tables = len(mvmt.table_settings_by_zb_table_number)
        boards_per_round_per_tournament = num_tables * mvmt.boards_per_round_per_table
        rv = divmod(num_completed_hands, boards_per_round_per_tournament)
        logger.debug(f"{num_completed_hands=} {boards_per_round_per_tournament=} => {rv=}")
        return rv

    def pairs_from_existing_hands(self) -> Generator[app.utils.movements.Pair]:
        """I examine my hands, and for each, I *assume* that N and S are partners, as are E and W.  This avoids chaos if a partnership has dissolved since the tournament's signup deadline expired."""
        pairs: set[tuple[Player, Player]] = set()
        for h in (
            self.hands()
            .select_related(*app.models.common.attribute_names)
            .select_related(*[f"{d}__user" for d in app.models.common.attribute_names])
        ):
            p1 = tuple(sorted([h.North, h.South], key=operator.attrgetter("pk")))
            p2 = tuple(sorted([h.East, h.West], key=operator.attrgetter("pk")))
            pairs.add(p1)
            pairs.add(p2)
        for p in pairs:
            yield app.utils.movements.Pair(
                id_=(p[0].pk, p[1].pk), names=f"{p[0].name}, {p[1].name}"
            )

    def create_hands_for_round(self, *, zb_round_number: int) -> list[Hand]:
        rv: list[Hand] = []
        for zb_table_number in range(self.get_movement().num_rounds):
            new_hand = app.models.Hand.objects.create_next_hand_at_table(
                self, zb_table_number=zb_table_number, zb_round_number=zb_round_number
            )
            assert new_hand is not None
            rv.append(new_hand)

        return rv

    def _cache_key(self) -> str:
        return f"tournament:{self.pk}"

    def _cache_set(self, value: app.utils.movements.Movement) -> None:
        assert_type(value, app.utils.movements.Movement)
        cache.set(self._cache_key(), value)

    def _cache_get(self) -> app.utils.movements.Movement | None:
        rv = cache.get(self._cache_key())
        assert_type(rv, app.utils.movements.Movement | None)
        return rv

    def get_movement(self) -> app.utils.movements.Movement:
        if (_movement := self._cache_get()) is None:
            if self.hands().exists():
                pairs = list(self.pairs_from_existing_hands())
            else:
                assert self.signup_deadline_has_passed(), (
                    f"t#{self.display_number}: Cannot create a movement until the signup deadline ({self.signup_deadline}) has passed"
                )
                pairs = list(self.signed_up_pairs())
                logger.debug(f"signed_up_pairs => {pairs=}")

            if not pairs:
                msg = f"Tournament #{self.display_number}: Can't create a movement with no pairs!"
                raise NoPairs(msg)

            _movement = app.utils.movements.Movement.from_pairs(
                boards_per_round_per_table=self.boards_per_round_per_table,
                pairs=pairs,
                tournament=self,
            )
            assert _movement.num_phantoms == 0
            self._cache_set(_movement)

        return _movement

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
        if self.is_complete:
            return Complete

        now = timezone.now()
        if now < self.signup_deadline:
            return OpenForSignup
        if now < self.play_completion_deadline:
            return Running

        logger.warning("I confess I don't understand how we got here.")
        return Complete

    def status_str(self) -> str:
        return self.status().__name__

    def short_string(self) -> str:
        return f"tournament #{self.display_number}"

    def sign_up_player_and_partner(self, player: Player) -> None:
        if self.status() is not OpenForSignup:
            msg = f"Tournament #{self.display_number} is {self.status_str()}, not open for signup; the signup deadline was {self.signup_deadline}"
            raise NotOpenForSignupError(msg)
        if player.partner is None:
            raise PlayerNeedsPartnerError(f"{player.name} has no partner")
        if any(p.currently_seated for p in (player, player.partner)):
            raise PlayerNotSeatedError(
                f"At least one of {(player.name, player.partner.name)} is currently seated"
            )

        num_created = 0
        for p in (player, player.partner):
            _, created = app.models.TournamentSignup.objects.get_or_create(
                defaults=dict(tournament=self), player=p
            )
            if created:
                num_created += 1

    def signed_up_pairs(self) -> Generator[app.utils.movements.Pair]:
        seen: set[PK] = set()

        for p in (
            self.signed_up_players()
            .select_related("user")
            .select_related("partner")
            .select_related("partner__user")
        ):
            if p.pk not in seen and p.partner.pk not in seen:
                names = f"{p.name}, {p.partner.name}"
                yield app.utils.movements.Pair(id_=[p.pk, p.partner.pk], names=names)
                seen.add(p.pk)
                seen.add(p.partner.pk)

    def signed_up_players(self) -> models.QuerySet:
        from app.models import Player

        return Player.objects.filter(
            player__in=app.models.TournamentSignup.objects.filter(tournament=self).values_list(
                "player", flat=True
            )
        )

    def __repr__(self) -> str:
        return f"<Tournament #{self.display_number} pk={self.pk}>"

    def __str__(self) -> str:
        rv = f"{self.short_string()}; {self.status().__name__}"
        if self.status() is not Complete:
            num_completed = self.hands().filter(is_complete=True).count()
            rv += f"; {num_completed} hands played"

        return rv

    def hands(self) -> models.QuerySet:
        from app.models import Hand

        return Hand.objects.filter(board__in=self.board_set.all()).distinct()

    def abandon_all_hands(self, reason: str) -> None:
        with transaction.atomic():
            player: app.models.Player

            for player in self.players():
                player.abandon_my_hand(reason=reason)
                player.save()

    def maybe_complete(self) -> None:
        with transaction.atomic():
            if self.hands().count() == 0 and self.play_completion_deadline_has_passed():
                logger.info(
                    "%s: Huh, the play completion deadline passed without any hands being played! I'm deleting myself.",
                    self,
                )
                self.delete()
                return

            if self.is_complete:
                logger.info("Pff, no need to complete '%s' since it's already complete.", self)
                return

            all_hands_are_complete = (
                self.hands().exists() and not self.hands().filter(is_complete=False).exists()
            )

            if all_hands_are_complete or self.play_completion_deadline_has_passed():
                self.completed_at = (
                    timezone.now() if all_hands_are_complete else self.play_completion_deadline
                )
                self.save()

    def save(self, *args, **kwargs) -> None:
        if self.is_complete:
            if (victims := app.models.TournamentSignup.objects.filter(tournament=self)).exists():
                logger.debug(
                    "Deleting %s because tournament #%s is complete", victims, self.display_number
                )
                victims.delete()

        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.CheckConstraint(  # type: ignore[call-arg]
                name="%(app_label)s_%(class)s_play_deadline_must_follow_signup_deadline",
                condition=(
                    models.Q(play_completion_deadline__isnull=True)
                    | models.Q(play_completion_deadline__gt=models.F("signup_deadline"))
                ),
            ),
            models.UniqueConstraint(  # type: ignore[call-arg]
                name="%(app_label)s_%(class)s_display_number_unique",
                fields=["display_number"],
            ),
        ]


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ["display_number", "is_complete", "signup_deadline", "play_completion_deadline"]
