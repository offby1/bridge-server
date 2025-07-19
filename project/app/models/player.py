from __future__ import annotations

import datetime
import logging
import re
from typing import TYPE_CHECKING

import more_itertools

import bridge.auction
import bridge.card
import bridge.seat
import bridge.table
from django.contrib import admin, auth
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django_eventstream import send_event  # type: ignore [import-untyped]
from django_extensions.db.models import TimeStampedModel  # type: ignore [import-untyped]
from faker import Faker

from .board import Board
from .common import attribute_names
from .message import Message
from .playaz import WireCharacterProvider
from .types import PK_from_str

if TYPE_CHECKING:
    from .hand import Hand
    from .types import PK
    import app.models

logger = logging.getLogger(__name__)


JOIN = "partnerup"
SPLIT = "splitsville"


class PlayerManager(models.Manager):
    def _update_redundant_fields(self):
        for instance in self.all():
            instance._update_redundant_fields()

    @staticmethod
    def _find_unused_username(prefix=""):
        fake = Faker()
        Faker.seed(0)
        fake.add_provider(WireCharacterProvider)

        while True:
            # Ensure neither the prefixed, nor the unprefixed, version exists.
            unprefixed_candidate = fake.unique.playa().lower()
            candidates = [unprefixed_candidate, prefix + unprefixed_candidate]
            if not auth.models.User.objects.filter(username__in=candidates).exists():
                return candidates[-1]

    def create_synthetic(self) -> Player:
        new_user = auth.models.User.objects.create_user(
            username=self._find_unused_username(prefix="_")
        )

        # Handy for hackin', but you don't want this active in prod
        ####################
        # logger.warning(f"Hard-coding known password for {new_user.username=}")
        # new_user.password = "pbkdf2_sha256$870000$2hIscex1sYiQd86rzIuNEb$C1t3fgjQJ00VLQA6H7Hg25GGjkyLc9CBfkzNTSbqYTU="
        # new_user.save()
        ####################

        return Player.objects.create(synthetic=True, allow_bot_to_play_for_me=True, user=new_user)

    def get_or_create_synthetic(self, **exclude_kwargs) -> tuple[Player, bool]:
        existing = (
            Player.objects.filter(synthetic=True, partner__isnull=True)
            .exclude(**exclude_kwargs)
            .first()
        )
        if existing is not None:
            return existing, False

        return self.create_synthetic(), True

    def ensure_eight_players_signed_up(self, *, tournament: app.models.Tournament) -> None:
        with transaction.atomic():
            the_eight = [
                player for player in self.filter(tournamentsignup__tournament=tournament)[0:8]
            ]

            while len(the_eight) < 8:
                p, created = self.get_or_create_synthetic(pk__in=[p.pk for p in the_eight])
                logger.info("%s %s", "created" if created else "reused", p)
                the_eight.append(p)

            # now pair 'em up and sign 'em up
            unpartnered = [p for p in the_eight if p.partner is None]

            for chunk in more_itertools.chunked(unpartnered, 2):
                if len(chunk) == 2:
                    p1, p2 = chunk
                    p1.partner_with(p2)

            for p in the_eight:
                tournament.sign_up_player_and_partner(p)

    def get_from_user(self, user):
        return self.get(user=user)

    def get_by_name(self, name):
        return self.get(user__username=name)

    def currently_seated(self) -> models.QuerySet:
        return self.filter(current_hand__isnull=False)


class PlayerException(Exception):
    pass


class TooManyBots(PlayerException):
    pass


class PartnerException(PlayerException):
    pass


class Player(TimeStampedModel):
    objects = PlayerManager()

    user = models.OneToOneField(
        auth.models.User,
        on_delete=models.CASCADE,
    )

    # TODO -- conceptually, this oughta be a OneToOneField, no?

    # On the other hand -- do I need this at all?  If our player is seated, then we can deduce his partner by seeing
    # who's sitting across from him.  But then if the partnership isn't seated, I'm outta luck.
    partner = models.ForeignKey["Player"](
        "Player", null=True, blank=True, on_delete=models.SET_NULL
    )

    allow_bot_to_play_for_me = models.BooleanField(default=False)
    synthetic = models.BooleanField(default=False)

    messages_for_me = GenericRelation(
        Message,
        related_query_name="player_recipient",
        content_type_field="recipient_content_type",
        object_id_field="recipient_object_id",
    )

    hands_by_board_cache: dict[Board, Hand]

    # This is redundant -- it could be computed from the transcript -- but keeping it here saves time by in effect
    # caching it.
    current_hand = models.ForeignKey("Hand", on_delete=models.CASCADE, null=True)

    def _update_redundant_fields(self):
        import app.models

        for h in app.models.Hand.objects.filter(
            app.models.Hand.has_player(self), is_complete=False, abandoned_because__isnull=True
        ):
            for direction_name in attribute_names:
                if getattr(h, direction_name) == self:
                    self.current_hand = h
                    self.save(update_fields=["current_hand"])

    def controls_seat(self, *, seat: bridge.seat.Seat, right_this_second: bool) -> bool:
        # Take declarer & dummy into account.  This isn't all that complex, but I keep getting it wrong, so it needs to
        # be in one place, and tested.

        hand = self.current_hand
        if hand is None:
            logger.info(
                "%s", f"{self.name} may not call or play now because they have no current hand."
            )
            return False

        # simple case: no dummy yet
        seats_by_player = {getattr(hand, s.name): set([s]) for s in bridge.seat.Seat}

        # Now update that dict, taking into account declarer & dummy
        if hand.play_set.count() >= 1:
            seats_by_player[hand.model_dummy] = set()
            seats_by_player[hand.model_declarer].add(hand.dummy.seat)

        rv = seat in seats_by_player[self]
        if right_this_second:
            rv = rv and seat == (hand.next_seat_to_play or hand.next_seat_to_call)
        return rv

    # *all* hands to which we've ever been assigned, regardless of whether they're complete or abandoned
    @property
    def hands_played(self) -> models.QuerySet:
        from app.models import Hand

        return Hand.objects.all().filter(Hand.has_player(self))

    @property
    def boards_played(self) -> models.QuerySet:
        return Board.objects.filter(pk__in=self.hands_played)

    def last_action(self) -> tuple[datetime.datetime, str]:
        rv = (self.created, "joined")
        if self.user.last_login and self.user.last_login > rv[0]:
            rv = (self.user.last_login, "logged in")
        if (h := self.hands_played.order_by("-id").first()) is not None:
            # TODO: somehow narrow stuff down to the most recent action that *we* took in this hand, as opposed to my
            # partner or opponents
            hand_last_action = h.last_action()
            if hand_last_action[0] > rv[0]:
                rv = hand_last_action

        return rv

    def unseat_partnership(self, reason: str | None = None) -> None:
        with transaction.atomic():
            for p in (self, getattr(self, "partner")):
                if p is not None and p.currently_seated:
                    p.abandon_my_hand(reason=reason)

    def abandon_my_hand(self, reason: str | None = None) -> None:
        with transaction.atomic():
            if (h := self.current_hand) is not None:
                h.abandoned_because = reason or f"{self.name} left"
                h.save()

                self.current_hand = None
                self.save()

                logger.debug(
                    "%s",
                    f"{self} ({id(self)}) abandoned hand {h} ({h=}) because {h.abandoned_because}",
                )

    @property
    def event_HTML_hand_channel(self):
        return f"player:html:hand:{self.pk}"

    @staticmethod
    def player_pk_from_event_HTML_hand_channel(cn: str) -> PK | None:
        if (m := re.match(r"player:html:(?:hand|chat):(?P<player_id>.*)", cn)) is not None:
            return PK_from_str(m.groups()[0])

        return None

    @property
    def event_JSON_hand_channel(self):
        return f"player:json:{self.pk}"

    @staticmethod
    def player_pk_from_event_JSON_hand_channel(cn: str) -> PK | None:
        if (m := re.match(r"player:json:(?P<player_id>.*)", cn)) is not None:
            return PK_from_str(m.groups()[0])

        return None

    def toggle_bot(self, desired_state: bool | None = None) -> None:
        with transaction.atomic():
            if desired_state is None:
                desired_state = not self.allow_bot_to_play_for_me

            self.allow_bot_to_play_for_me = desired_state
            self.save()

    def save(self, *args, **kwargs) -> None:
        self._check_synthetic()
        super().save(*args, **kwargs)

    def _check_synthetic(self) -> None:
        if not self.pk:
            return
        original = Player.objects.get(pk=self.pk)
        if self.synthetic != original.synthetic:
            raise ValidationError("The 'synthetic' field cannot be changed.")

    def libraryThing(self) -> bridge.table.Player:
        direction_name = self.current_direction()

        if direction_name is None:
            msg = f"{self} is not seated, so cannot be converted to a bridge-library Player"
            raise PlayerException(msg)

        return bridge.table.Player(
            seat=bridge.seat.Seat(direction_name[0].upper()),
            name=self.name,
        )

    @property
    def looking_for_partner(self):
        return self.partner is None

    def _send_partnership_messages(self, *, action, old_partner_pk=None):
        if action == JOIN:
            send_event(
                *Message.create_lobby_event_args(
                    from_player=self,
                    message=f"Partnered with {self.partner.name}",
                ),
            )

        # We always send two arrays, even though one is empty.  That's because I'm too stupid a JS programmer to deal
        # with missing attributes.
        data = {"split": [], "joined": []}

        if action == SPLIT:
            data["split"] = [old_partner_pk, self.pk]
        else:
            data["joined"] = [self.partner.pk, self.pk]

        channel = "partnerships"

        send_event(
            channel=channel,
            event_type="message",
            data=data,
        )

    def partner_with(self, other):
        with transaction.atomic():
            if self.partner not in (None, other):
                msg = f"Cannot partner with {other.name=} cuz I'm already partnered with {self.partner.name=}"
                raise PartnerException(
                    msg,
                )
            if other.partner not in (None, self):
                msg = f"Cannot partner {other=} with {self=} cuz they are already partnered with {other.partner=}"
                raise PartnerException(
                    msg,
                )

            self.partner = other
            other.partner = self

            self.save()
            other.save()
            self._send_partnership_messages(action=JOIN)

    def break_partnership(self):
        with transaction.atomic():
            if self.partner is None:
                msg = "Cannot break up with partner 'cuz we don't *have* a partner"
                raise PartnerException(
                    msg,
                )

            if self.partner.partner is None:
                msg = "Oh shit -- our partner doesn't have a partner"
                raise PartnerException(
                    msg,
                )

            logger.debug(
                "%s is calling it splits with their partner %s", self.name, self.partner.name
            )
            old_partner_pk = self.partner.pk

            import app.models

            evictees = app.models.TournamentSignup.objects.filter(player__in={self, self.partner})
            if not evictees:
                logger.debug(
                    "Neither %s nor %s were signed up for any tournaments; no TournamentSignups to delete",
                    self.name,
                    self.partner.name,
                )
            else:
                logger.debug(
                    "About to remove %s",
                    ", ".join(
                        [
                            f"{su.player.name} from signups for t#{su.tournament.display_number}"
                            for su in evictees
                        ]
                    ),
                )
                evictees.delete()

            self.partner.partner = None
            self.partner.abandon_my_hand()
            self.partner.save(update_fields=["partner"])

            self.partner = None
            self.abandon_my_hand()  # superfluous, but harmless
            self.save(update_fields=["partner"])

        self._send_partnership_messages(action=SPLIT, old_partner_pk=old_partner_pk)

    @property
    def currently_seated(self) -> bool:
        return self.current_hand is not None

    def current_hand_and_direction(self) -> tuple[Hand, str] | None:
        """The string is a capitalized word, like "East"."""
        if self.current_hand is not None:
            return self.current_hand, self.current_direction(current_hand=self.current_hand)

        return None

    def direction_at_hand(self, h: Hand) -> str:
        for direction_name in h.direction_names:
            if getattr(h, direction_name) == self:
                return direction_name

        assert False, f"some idiot called me for {h} when {self.name} never played it"

    def current_direction(self, current_hand: Hand | None = None) -> str | None:
        """A whole, capitalized, word like 'East'"""
        if current_hand is None:
            current_hand = self.current_hand

        if current_hand is None:
            return None

        for d in attribute_names:
            if getattr(current_hand, d) == self:
                return d

        raise Exception(
            "%s", f"Oy! {self} has {current_hand=} but none of {attribute_names} are us?"
        )

    def dealt_cards(self) -> list[bridge.card.Card]:
        ch = self.current_hand_and_direction()

        if ch is None:
            msg = f"{self} is not seated, so has no cards"
            raise PlayerException(msg)

        current_hand, direction_name = ch
        return current_hand.board.cards_for_direction_string(direction_name)

    def has_played_hand(self, hand: Hand) -> bool:
        return hand in self.hands_played.all()

    def cache_get(self, *, board: Board) -> Hand | None:
        cache = getattr(self, "hands_by_board_cache", {})
        return cache.get(board)

    def cache_set(self, *, board: Board, hand: Hand) -> None:
        cache = getattr(self, "hands_by_board_cache", {})
        cache[board] = hand
        setattr(self, "hands_by_board_cache", cache)

    def hand_at_which_we_played_board(self, board: Board) -> Hand | None:
        if (hit := self.cache_get(board=board)) is not None:
            return hit

        rv: Hand | None = self.hands_played.filter(board=board).first()
        if rv is not None:
            self.cache_set(board=board, hand=rv)
        return rv

    def has_seen_board_at(self, board: Board, seat: bridge.seat.Seat) -> bool:
        return board in self.boards_played.all()

    @cached_property
    def name(self):
        return self.user.username

    def display_name(self) -> str:
        return f"{self.pk}:{self.as_link()}"

    def as_link(self, style=""):
        name = self.name
        if self.synthetic:
            name = format_html("<i>{}</i>", self.name)
        style_attribute = "" if not style else f'style="{style}"'
        return format_html(
            f'<a {style_attribute} href="{{}}">{{}}</a>',
            reverse("app:player", kwargs={"pk": self.pk}),
            name,
        )

    def create_synthetic_partner(self) -> Player:
        with transaction.atomic():
            if self.partner is not None:
                return self.partner

            existing = Player.objects.filter(synthetic=True).filter(partner__isnull=True)
            if existing.exists():
                raise PartnerException(
                    f"There are already existing, unpartnered synths {[s.name for s in existing.all()]}"
                )
            new_player = Player.objects.create_synthetic()
            new_player.partner = self
            self.partner = new_player
            self.save()
            new_player.save()
            return self.partner

    class Meta:
        ordering = ["user__username"]
        constraints = [
            models.CheckConstraint(  # type: ignore [call-arg]
                name="%(app_label)s_%(class)s_cant_be_own_partner",
                condition=models.Q(partner__isnull=True) | ~models.Q(partner_id=models.F("id")),
            ),
            models.CheckConstraint(
                name="synthetic_players_must_allow_bot_to_play_for_them",
                condition=models.Q(synthetic=False) | models.Q(allow_bot_to_play_for_me=True),
            ),  # type: ignore [call-arg]
        ]

    def __repr__(self) -> str:
        return f"modelPlayer{vars(self)}"

    def __str__(self):
        return self.name


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ["name", "synthetic", "allow_bot_to_play_for_me"]
