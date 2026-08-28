from __future__ import annotations

import collections
import datetime
import logging
import operator
from typing import TYPE_CHECKING, Literal

from django.contrib import admin
from django.core.cache import cache
from django.db import IntegrityError, models, transaction
from django.utils import timezone

import app.models
import app.models.common
import app.utils.movements
import app.utils.scoring
from app.models.signups import TournamentSignup
from app.models.types import PK
from app.models.utils import assert_type
from bridge.xscript import BrokenDownScore

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
        assert tour.hands().count() == tour.get_movement().num_rounds, (
            f"Oy! {tour.hands().count()=} != {tour.get_movement().num_rounds=}"
        )

        if tour.play_completion_deadline == WAY_DISTANT_PLAY_COMPLETION_DEADLINE:
            tour.play_completion_deadline = tour.compute_play_completion_deadline()
            tour.save()


# How long we're willing to sleep when no deadline is pending.  The ceiling is what
# covers a tournament created after we worked out when to wake up.
WAKE_AT_LEAST_EVERY = datetime.timedelta(seconds=30)


def advance_expired_tournaments() -> datetime.datetime:
    """Apply every tournament deadline that has passed; return when to look again.

    The `tournament_clock` management command calls this in a loop.  It used to run at
    the end of every HTTP request, throttled to once a minute, which meant deadlines
    were honoured only as often as somebody happened to send a request -- in production
    that was Prometheus scraping /metrics, which is a strange thing for the rules of the
    game to depend on.

    Running this twice, or in two processes at once, is safe: each transition is claimed
    in the database rather than checked in Python.
    """
    for tour in Tournament.objects.incompletes().filter(signup_deadline__isnull=False):
        if tour.play_completion_deadline_has_passed():
            _finish_play(tour)
        elif tour.signup_deadline_has_passed():
            _start_play(tour)

    return _next_deadline_after(timezone.now())


def _finish_play(tour: Tournament) -> None:
    """Abandon whatever is still in progress, and tell the tables about it."""
    with transaction.atomic():
        # The claim and the mutual exclusion are the same statement: this UPDATE holds
        # the row until we commit, so a second clock blocks here, then matches zero rows
        # and leaves.  No advisory lock required.
        deadline = tour.play_completion_deadline
        if not Tournament.objects.filter(pk=tour.pk, completed_at__isnull=True).update(
            completed_at=deadline
        ):
            logger.debug("%s: another clock completed this one first", tour)
            return

        deadline_str = deadline.isoformat()
        # Each hand's play-completion-deadline TABLE event now comes from
        # app.broadcast.broadcast_after_hand_change, driven by the abandoned_because
        # UPDATE these abandonments produce (see docs/README.listen-notify.md).
        tour.abandon_all_hands(reason=f"play completion deadline ({deadline_str}) has passed")

        # A finished tournament's signups are dead weight; drop them here too, the
        # way Tournament.save does on the normal (all-hands-played) completion path.
        # Otherwise a player is left signed up for a completed tournament
        # (TournamentSignup.player is OneToOne), which blocks their next signup.
        TournamentSignup.objects.filter(tournament=tour).delete()


def _start_play(tour: Tournament) -> None:
    """Turn a closed signup list into hands."""
    # There's no column to claim here: play_completion_deadline can't be computed until
    # the movement exists, which needs the hands.  So we let the database refuse the
    # duplicate -- Hand is unique on (board, table_display_number) -- and because
    # _do_signup_expired_stuff is one transaction, the loser's synthetic players roll
    # back along with its hands.  The loser wastes work; it doesn't corrupt anything.
    try:
        _do_signup_expired_stuff(tour)
    except IntegrityError:
        logger.info("%s: another clock created these hands first", tour)


def _next_deadline_after(now: datetime.datetime) -> datetime.datetime:
    """The soonest deadline we still owe, or a ceiling if there isn't one."""
    incompletes = Tournament.objects.incompletes()

    candidates = [
        incompletes.filter(signup_deadline__gt=now).aggregate(
            soonest=models.Min("signup_deadline")
        )["soonest"],
        incompletes.filter(play_completion_deadline__gt=now)
        .exclude(play_completion_deadline=WAY_DISTANT_PLAY_COMPLETION_DEADLINE)
        .aggregate(soonest=models.Min("play_completion_deadline"))["soonest"],
    ]

    return min(
        [d for d in candidates if d is not None] + [now + WAKE_AT_LEAST_EVERY],
    )


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

    completed_at = models.DateTimeField(null=True, blank=True)

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

    def matchpoints_by_pair(
        self,
    ) -> dict[tuple[app.models.player.Player, app.models.player.Player], tuple[float, float]]:
        # Convert the final score, which might be zero, into a dict of kwargs
        def consistent_score(fs: BrokenDownScore | Literal[0]) -> dict[str, int]:
            if fs == 0:
                return {"ns_raw_score": 0, "ew_raw_score": 0}
            return {"ns_raw_score": fs.north_south_points, "ew_raw_score": fs.east_west_points}

        def enriched(qs: models.QuerySet) -> models.QuerySet:
            return (
                qs.select_related(*app.models.common.attribute_names)
                .select_related("board")
                .select_related(*[f"{d}__user" for d in app.models.common.attribute_names])
            )

        hands = [
            app.utils.scoring.Hand(
                ns_id=(h.North, h.South),
                ew_id=(h.East, h.West),
                board_id=h.board.pk,
                **consistent_score(h.get_xscript().final_score()),
            )
            for h in enriched(self.hands().filter(abandoned_because__isnull=True, is_complete=True))
        ]

        withdrawn = app.models.TournamentWithdrawal.objects.pks_withdrawn_from(self)
        adjustments = [
            self._adjusted_score_for(h, withdrawn=withdrawn)
            for h in enriched(self.hands().filter(abandoned_because__isnull=False))
        ]

        scorer = app.utils.scoring.Scorer(hands=hands, adjustments=adjustments)
        # Return Player objects, not HTML strings
        return scorer.matchpoints_by_pairs()

    def _adjusted_score_for(
        self, hand: Hand, *, withdrawn: set[int]
    ) -> app.utils.scoring.AdjustedHand:
        """Apportion Law 12's artificial score for a board that yielded no result.

        A pair who walked out are directly at fault and get average minus; whoever they
        were down to play are in no way at fault and get average plus.  When neither pair
        withdrew -- the play-completion deadline ran out on a table that was still going,
        say -- we hold both partly at fault and give each of them average.
        """
        ns_walked_out = any(p.pk in withdrawn for p in (hand.North, hand.South))
        ew_walked_out = any(p.pk in withdrawn for p in (hand.East, hand.West))

        if not (ns_walked_out or ew_walked_out):
            ns_fraction = ew_fraction = app.utils.scoring.PARTLY_AT_FAULT
        else:
            ns_fraction = (
                app.utils.scoring.AT_FAULT if ns_walked_out else app.utils.scoring.NOT_AT_FAULT
            )
            ew_fraction = (
                app.utils.scoring.AT_FAULT if ew_walked_out else app.utils.scoring.NOT_AT_FAULT
            )

        return app.utils.scoring.AdjustedHand(
            ns_id=(hand.North, hand.South),
            ew_id=(hand.East, hand.West),
            board_id=hand.board.pk,
            ns_fraction=ns_fraction,
            ew_fraction=ew_fraction,
        )

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
        """How many rounds are behind us, if the latest one is over; otherwise None.

        A hand is *settled* when nobody can act on it any more: either it was played to
        the end (`is_complete`) or somebody gave up on it (`abandoned_because`).  A table
        is done with a round once it has settled every board in that round's group -- or
        as soon as one of its hands is abandoned, since an abandoned table deals itself
        no further boards.  The round is over when every table is done with it.

        Counting settled hands against the total the movement calls for does not work,
        precisely because an abandoned table stops short: the count never reaches the
        total.  That is what used to freeze every table in the tournament when a single
        pair walked out (TODO.txt, the Splitsville item).
        """
        hands = list(self.hands().select_related("board"))
        if not hands:
            return None

        zb_round_number = max(app.utils.movements._zb_round_number(h.board.group) for h in hands)

        if not self._round_is_over(zb_round_number=zb_round_number, hands=hands):
            return None

        return zb_round_number + 1

    def _round_is_over(self, *, zb_round_number: int, hands: list[Hand]) -> bool:
        mvmt = self.get_movement()
        group = app.utils.movements._group_letter(zb_round_number)

        hands_by_table: dict[int | None, list[Hand]] = collections.defaultdict(list)
        for h in hands:
            if h.board.group == group:
                hands_by_table[h.table_display_number].append(h)

        # A table with no hand in this group hasn't started the round yet.
        if len(hands_by_table) < len(mvmt.table_settings_by_zb_table_number):
            return False

        for table_hands in hands_by_table.values():
            if any(h.is_abandoned for h in table_hands):
                continue
            if sum(1 for h in table_hands if h.is_complete) < mvmt.boards_per_round_per_table:
                return False

        return True

    def record_boards_this_table_will_not_play(self, *, hand: Hand) -> None:
        """Write down the boards a table won't reach, now that one of its hands is dead.

        Only the boards of the round it was in the middle of: later rounds get theirs
        when we deal them.  Without this, the pair who were left sitting there would get
        an adjusted score for the boards they were denied in later rounds but nothing at
        all for the rest of this one.

        Does nothing unless somebody at the table has withdrawn -- `_create_hand_with`
        would otherwise seat people at these boards, which is right when a hand was
        abandoned for some other reason.
        """
        import app.models

        withdrawn = app.models.TournamentWithdrawal.objects.pks_withdrawn_from(self)
        if not any(getattr(hand, d).pk in withdrawn for d in app.models.common.attribute_names):
            return

        assert hand.table_display_number is not None
        zb_round_number = app.utils.movements._zb_round_number(hand.board.group)

        with transaction.atomic():
            for _ in range(self.get_movement().boards_per_round_per_table):
                if (
                    app.models.Hand.objects.create_next_hand_at_table(
                        self,
                        zb_table_number=hand.table_display_number - 1,
                        zb_round_number=zb_round_number,
                    )
                    is None
                ):
                    return

    def maybe_advance_round(self) -> bool:
        """If the latest round is over, start the next one (or finish the tournament).

        Returns whether the round was over, so that a caller who has just settled one
        hand can tell whether the table it was at should deal itself another board.

        We keep going while each round we deal is itself already over.  A round is born
        settled when every table in it was due to be played by somebody who has since
        withdrawn, and nothing else would come along to notice: no hand of it will ever
        be played, and nobody will abandon one either.
        """
        advanced = False

        with transaction.atomic():
            while (num_completed_rounds := self.the_round_just_ended()) is not None:
                advanced = True

                if num_completed_rounds >= self.get_movement().num_rounds:
                    self.maybe_complete()
                    break

                self.create_hands_for_round(zb_round_number=num_completed_rounds)

        return advanced

    def rounds_played(self) -> tuple[int, int]:
        """
        Returns a tuple: the number of *completed* rounds, and the number of :model:`app.hand` s played in the current round.

        Only completed hands count, so this understates progress in a tournament where
        somebody abandoned a hand: those hands are never coming back, but this arithmetic
        goes on waiting for them.  `the_round_just_ended` is the one that decides whether
        play moves on, and it does not use this.  Today nothing outside the tests calls
        this; don't reach for it to answer "is the round over".
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

            # We deal one board per table here and let each table deal itself the next
            # as it finishes one.  A table with nobody at it never finishes anything, so
            # the rest of its round would go unrecorded -- and then the pairs who were
            # down to meet it on those boards would get no adjusted score for them,
            # while getting one for the round's first board.  Write them all down now.
            if new_hand.is_abandoned:
                self.record_boards_this_table_will_not_play(hand=new_hand)

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
                # Pad an odd number of pairs with a synthetic partnership so the
                # movement never needs a phantom.  _do_signup_expired_stuff does this
                # too, but the clock may not have got to this tournament yet, so a page
                # view can reach here first -- and a phantom would otherwise trip the
                # assertion below.
                TournamentSignup.objects.create_synths_for(self)
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

        for p in (player, player.partner):
            su, created = app.models.TournamentSignup.objects.get_or_create(
                defaults=dict(tournament=self), player=p
            )
            # A player has at most one signup (TournamentSignup.player is
            # OneToOne). If they had a leftover one -- e.g. for a tournament that
            # has since finished (completed tournaments finished via the deadline
            # path keep their signup rows) -- re-point it here rather than leaving
            # them stuck enrolled nowhere useful.
            if not created and su.tournament_id != self.pk:
                su.tournament = self
                su.save()

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

        board_set = getattr(self, "board_set", None)
        if board_set is None:
            return Hand.objects.none()
        return Hand.objects.filter(board__in=self.board_set.all()).distinct()

    def abandon_all_hands(self, reason: str) -> None:
        with transaction.atomic():
            player: app.models.Player

            for player in self.players():
                # We are tearing the tournament down, so there is no next round to
                # start; advancing here would deal boards nobody will ever play.
                player.abandon_my_hand(reason=reason, advance_round=False)
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

            # Every hand is settled -- see `the_round_just_ended` -- when none is still
            # awaiting a call or a play.  An abandoned hand counts, so that a pair
            # walking out doesn't leave the tournament unfinishable.
            all_hands_are_settled = (
                self.hands().exists()
                and not self.hands()
                .filter(is_complete=False, abandoned_because__isnull=True)
                .exists()
            )

            logger.debug(
                "%s", f"{all_hands_are_settled=}; {self.play_completion_deadline_has_passed()=}"
            )
            if all_hands_are_settled or self.play_completion_deadline_has_passed():
                self.completed_at = (
                    timezone.now() if all_hands_are_settled else self.play_completion_deadline
                )
                if self.play_completion_deadline_has_passed():
                    self.abandon_all_hands(
                        reason=f"play completion deadline ({self.play_completion_deadline}) has passed"
                    )
                else:
                    self.players().update(current_hand=None, random_state=None)
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
    list_display = [
        "display_number",
        "is_complete",
        "signup_deadline_tz",
        "play_completion_deadline_tz",
    ]

    date_format = "%FT%T%z"

    @admin.display(description="signup deadline")
    def signup_deadline_tz(self, obj):
        return obj.signup_deadline.strftime(self.date_format) if obj.signup_deadline else None

    @admin.display(description="play completion deadline")
    def play_completion_deadline_tz(self, obj):
        return (
            obj.play_completion_deadline.strftime(self.date_format)
            if obj.play_completion_deadline
            else None
        )
