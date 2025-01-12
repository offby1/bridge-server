from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import bridge.auction
import bridge.card
import bridge.seat
import bridge.table
from django.contrib import admin, auth
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django_eventstream import send_event  # type: ignore [import-untyped]

from .board import Board
from .message import Message
from .seat import Seat

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from .hand import Hand
    from .table import Table

logger = logging.getLogger(__name__)


JOIN = "partnerup"
SPLIT = "splitsville"

MAX_BOT_PROCESSES = 40


class PlayerManager(models.Manager):
    def get_from_user(self, user):
        return self.get(user=user)

    def get_by_name(self, name):
        return self.get(user__username=name)


class PlayerException(Exception):
    pass


class TooManyBots(PlayerException):
    pass


class PartnerException(PlayerException):
    pass


class PlayerAdmin(admin.ModelAdmin):
    list_display = ["name", "allow_bot_to_play_for_me", "currently_seated"]
    list_filter = ["currently_seated"]


class Player(models.Model):
    if TYPE_CHECKING:
        seat_set = RelatedManager["Seat"]()

    display_name: str  # set by a view, from name_dir
    seat: Seat
    objects = PlayerManager()

    user = models.OneToOneField(
        auth.models.User,
        on_delete=models.CASCADE,
    )

    # TODO -- conceptually, this oughta be a OneToOneField, no?

    # On the other hand -- do I need this at all?  If our player is seated, then we can deduce his partner by seeing
    # who's sitting across from him.  But then if the partnership isn't seated, I'm outta luck.
    partner = models.ForeignKey("Player", null=True, blank=True, on_delete=models.SET_NULL)

    # This is semi-redundant.  If it's True, there *must* be some seat whose player is me; we check this in our `save` method.
    # If it's False, anything goes -- if there are no such seats, then it's fine (I've never been seated); otherwise,
    # those seats are historical, and I've since left my last table, and not chosen a new one.

    # This gets set to True when someone creates a Seat instance whose player is us; it gets set to False when our
    # partnership splits up.
    currently_seated = models.BooleanField(default=False)

    messages_for_me = GenericRelation(
        Message,
        related_query_name="player_recipient",
        content_type_field="recipient_content_type",
        object_id_field="recipient_object_id",
    )

    @property
    def event_channel_name(self):
        return f"system:player:{self.pk}"

    def toggle_bot(self) -> None:
        with transaction.atomic():
            # If they are asking to enable the bot, ensure there aren't already too many bots.
            if not self.allow_bot_to_play_for_me:
                c = BotPlayer.objects.count()
                if c >= MAX_BOT_PROCESSES:
                    msg = f"There are already {c} bots; no bot for you"
                    raise TooManyBots(msg)

                BotPlayer.objects.create(player=self)
            else:
                BotPlayer.objects.filter(player=self).delete()

    def save(self, *args, **kwargs) -> None:
        self._check_current_seat()
        super().save(*args, **kwargs)

    @property
    def allow_bot_to_play_for_me(self) -> bool:
        return BotPlayer.objects.filter(player_id=self.pk).exists()

    def _check_current_seat(self) -> None:
        if not self.currently_seated:
            return

        my_seats = Seat.objects.filter(player=self)

        assert (
            my_seats.exists()
        ), f"{self.currently_seated=} and yet I cannot find a table at which I am sitting"

    def libraryThing(self) -> bridge.table.Player:
        seat = self.current_seat

        assert seat is not None

        return bridge.table.Player(
            seat=seat.libraryThing,
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
                msg = f"Cannot partner with {other=} cuz I'm already partnered with {self.partner=}"
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

            old_partner_pk = self.partner.pk

            self.partner.partner = None
            self.partner.currently_seated = False

            self.partner.save(update_fields=["partner", "currently_seated"])

            self.partner = None
            self.currently_seated = False
            self.save(update_fields=["partner", "currently_seated"])

        self._send_partnership_messages(action=SPLIT, old_partner_pk=old_partner_pk)

    def current_table_pk(self) -> int | None:
        ct = self.current_table
        if ct is None:
            return None
        return ct.pk

    @property
    def current_table(self) -> Table | None:
        if self.current_seat is None:
            return None

        return self.current_seat.table

    @property
    def current_seat(self) -> Seat | None:
        if not self.currently_seated:
            return None

        return Seat.objects.filter(player=self).order_by("-id").first()

    def dealt_cards(self) -> list[bridge.card.Card]:
        seat = self.current_seat
        assert seat is not None
        return seat.table.current_hand.board.cards_for_direction(seat.direction)

    @property
    def hands_played(self) -> models.QuerySet:
        from .hand import Hand
        from .table import Table

        my_seats = Seat.objects.filter(player=self)
        my_tables = Table.objects.filter(seat__in=my_seats)
        return Hand.objects.filter(table__in=my_tables)

    @property
    def boards_played(self):
        return self.hands_played.values_list("board", flat=True)

    def has_played_hand(self, hand: Hand) -> bool:
        return hand in self.hands_played.all()

    def hand_at_which_board_was_played(self, board: Board) -> Hand | None:
        from .hand import Hand
        from .table import Table

        qs = Hand.objects.filter(
            board=board,
            table__in=Table.objects.filter(
                pk__in=self.seat_set.values_list("table_id", flat=True).all()
            ).all(),
        ).all()
        return qs.first()

    def has_seen_board_at(self, board: Board, seat: bridge.seat.Seat) -> bool:
        what_they_can_see = board.what_can_they_see(player=self)
        if what_they_can_see == Board.PlayerVisibility.nothing:
            return False

        hand = self.hand_at_which_board_was_played(board)
        assert (
            hand is not None
        )  # what_they_can_see should have been PlayerVisibility.nothing in this case

        if what_they_can_see is Board.PlayerVisibility.own_hand:
            return hand.players_by_direction[seat.value] == self

        if what_they_can_see == Board.PlayerVisibility.dummys_hand:
            if hand.players_by_direction[seat.value] == self:
                return True
            dummy = hand.dummy
            return dummy is not None and dummy.seat == seat

        assert (
            what_they_can_see is Board.PlayerVisibility.everything
        ), f"{what_they_can_see=} but otta be everything"
        return True

    @cached_property
    def name(self):
        return self.user.username

    def name_dir(self, *, hand: Hand) -> str:
        direction = ""
        role = ""
        if self.has_played_hand(hand):
            seat = hand.table.seats.get(player=self)
            direction = f" ({seat.named_direction})"

            a: bridge.auction.Auction
            a = hand.get_xscript().auction
            if a.found_contract:
                assert isinstance(a.status, bridge.auction.Contract)
                assert a.declarer is not None
                assert a.dummy is not None
                if self.name == a.declarer.name:
                    role = "Declarer! "
                elif self.name == a.dummy.name:
                    role = "Dummy "
        bottiness = " (bot)" if self.allow_bot_to_play_for_me else ""

        return f"{self.pk}:{role}{self.user.username}{bottiness}{direction}"

    def as_link(self, style=""):
        return format_html(
            "<a style='{}' href='{}'>{}</a>",
            style,
            reverse("app:player", kwargs={"pk": self.pk}),
            str(self),
        )

    class Meta:
        ordering = ["user__username"]
        constraints = [
            models.CheckConstraint(  # type: ignore
                name="%(app_label)s_%(class)s_cant_be_own_partner",
                condition=models.Q(partner__isnull=True) | ~models.Q(partner_id=models.F("id")),
            ),
        ]

    def __repr__(self) -> str:
        return f"modelPlayer{vars(self)}"

    def __str__(self):
        return f"{self.name} ({'bot-powered' if self.allow_bot_to_play_for_me else 'independent'})"


class BotPlayer(models.Model):
    player = models.ForeignKey["Player"]("Player", on_delete=models.CASCADE)

    class Meta:
        db_table_comment = "Those players whose PKs appear here will have a bot play for them."


admin.site.register(Player, PlayerAdmin)
