from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any, Literal

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
        if tour.play_completion_deadline is None:
            tour.play_completion_deadline = tour.compute_play_completion_deadline()
            tour.save()


# TODO -- replace this with a scheduled solution -- see the "django-q2" branch
@receiver(request_finished)
@throttle(seconds=60)
def check_for_expirations(sender, **kwargs) -> None:
    logger.debug(f"{sender=} {kwargs=}")
    t: Tournament

    with transaction.atomic():
        incompletes = Tournament.objects.filter(is_complete=False, signup_deadline__isnull=False)

        logger.debug(f"{Tournament.objects.count()} tournaments: {incompletes=}")

        for t in incompletes:
            logger.debug("Checking '%s': ", t)
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
                t.abandon_all_hands(
                    reason=f"Play completion deadline ({t.play_completion_deadline.isoformat()}) has passed"
                )
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
    if as_of < signup_deadline:
        return OpenForSignup
    if play_completion_deadline is None:
        return ComputingPlayCompletionDeadline
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

    def get_or_create_tournament_open_for_signups(self, **kwargs) -> tuple[Tournament, bool]:
        with transaction.atomic():
            now = timezone.now()
            incomplete_and_open_tournaments_qs = self.filter(
                models.Q(signup_deadline__gte=now), is_complete=False
            )

            logger.debug(f"{now=} {incomplete_and_open_tournaments_qs=}")
            if not incomplete_and_open_tournaments_qs.exists():
                logger.debug(
                    "No tournament exists that is incomplete, and open for signup through %s, so we will create a new one",
                    now,
                )
                new_tournament = self.create(**kwargs)
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


# fmt:off

# fmt:on
class Tournament(models.Model):
    if TYPE_CHECKING:
        from app.models.board import Board

        board_set = RelatedManager["Board"]()

    boards_per_round_per_table = models.PositiveSmallIntegerField(default=3)

    # TODO -- replace this with a nullable `completed_at` DateTimefield
    is_complete = models.BooleanField(default=False)

    display_number = models.SmallIntegerField(unique=True)

    signup_deadline = models.DateTimeField(
        null=True, blank=True, default=None, db_comment="NULL means 'infintely far in the future'"
    )  # type: ignore[call-overload]
    play_completion_deadline = models.DateTimeField(
        null=True, blank=True, default=None, db_comment="NULL means 'infintely far in the future'"
    )  # type: ignore[call-overload]

    objects = TournamentManager()

    def matchpoints_by_pair(self) -> dict[tuple[str, str], tuple[int, float]]:
        # Convert the final score, which might be zero, into a dict of kwargs
        def consistent_score(fs: BrokenDownScore | Literal[0]) -> dict[str, int]:
            if fs == 0:
                return {"ns_raw_score": 0, "ew_raw_score": 0}
            return {"ns_raw_score": fs.north_south_points, "ew_raw_score": fs.east_west_points}

        def player_link(player_pk: PK) -> str:
            return app.models.Player.objects.get(pk=player_pk).as_link()

        hands = (
            app.utils.scoring.Hand(
                ns_id=(h.North.pk, h.South.pk),
                ew_id=(h.East.pk, h.West.pk),
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
            (player_link(k[0]), player_link(k[1])): v
            for k, v in scorer.matchpoints_by_pairs().items()
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
        expected = mvmt.boards_per_round_per_table * len(mvmt.table_settings_by_table_number)
        assert self.board_set.count() == expected, (
            f"Expected {mvmt.boards_per_round_per_table=} * {len(mvmt.table_settings_by_table_number)=} => {expected} boards, but got {self.board_set.count()}"
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
        num_completed_hands = sum([1 for h in self.hands().all() if h.is_complete])
        mvmt = self.get_movement()
        num_tables = len(mvmt.table_settings_by_table_number)
        boards_per_round_per_tournament = num_tables * mvmt.boards_per_round_per_table
        rv = divmod(num_completed_hands, boards_per_round_per_tournament)
        logger.debug(f"{num_completed_hands=} {boards_per_round_per_tournament=} => {rv=}")
        return rv

    @staticmethod
    def pairs_from_partnerships(players: models.QuerySet) -> Generator[app.utils.movements.Pair]:
        seen: set[PK] = set()

        for p in players:
            if p.pk not in seen and p.partner.pk not in seen:
                names = f"{p.name}, {p.partner.name}"
                yield app.utils.movements.Pair(id_=[p.pk, p.partner.pk], names=names)
                seen.add(p.pk)
                seen.add(p.partner.pk)

    def seated_pairs(self) -> Generator[app.utils.movements.Pair]:
        from app.models import Player

        yield from self.pairs_from_partnerships(Player.objects.currently_seated())

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

    def _cache_set(self, value: str) -> None:
        cache.set(self._cache_key(), value)

    def _cache_get(self) -> Any:
        return cache.get(self._cache_key())

    def get_movement(self) -> app.utils.movements.Movement:
        if (_movement := self._cache_get()) is None:
            logger.debug(f"{self.hands().count()} hands exist.")
            if self.hands().exists():
                # Collect all players who have played the hands.
                player_pks: set[PK] = set()
                for h in self.hands():
                    player_pks = player_pks.union(h.player_pks())
                from app.models import Player

                pairs = list(self.pairs_from_partnerships(Player.objects.filter(pk__in=player_pks)))
                logger.debug(f"self.pairs_from_partnerships => {pairs=}")
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

        if num_created > 0:
            logger.debug(
                "Just signed up partners %s and %s for tournament #%s",
                player.name,
                player.partner.name,
                self.display_number,
            )

    def signed_up_pairs(self) -> Generator[app.utils.movements.Pair]:
        players = (
            self.signed_up_players()
            .select_related("user")
            .select_related("partner")
            .select_related("partner__user")
        )

        yield from self.pairs_from_partnerships(players)

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
            num_completed = sum([h.is_complete for h in self.hands()])
            rv += f"; {num_completed} hands played"

        return rv

    def hands(self) -> models.QuerySet:
        from app.models import Hand

        return Hand.objects.filter(board__in=self.board_set.all()).distinct()

    def abandon_all_hands(self, reason: str) -> None:
        with transaction.atomic():
            for player in self.players():
                player.unseat_me(reason=reason)
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

            all_hands_are_complete = self.hands().exists()
            for h in self.hands():
                if not h.is_complete:
                    all_hands_are_complete = False
                    break

            if all_hands_are_complete or self.play_completion_deadline_has_passed():
                self.is_complete = True
                self.save()

    def save(self, *args, **kwargs) -> None:
        if self.is_complete:
            victims = app.models.TournamentSignup.objects.filter(tournament=self)
            logger.debug("Deleting %s", victims)
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
