from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import bridge.auction
import bridge.seat
import bridge.table
from django.contrib import admin, auth
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django_eventstream import send_event  # type: ignore

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


class PlayerManager(models.Manager):
    def get_from_user(self, user):
        return self.get(user=user)

    def get_by_name(self, name):
        return self.get(user__username=name)


class PlayerException(Exception):
    pass


class PartnerException(PlayerException):
    pass


class PlayerAdmin(admin.ModelAdmin):
    list_filter = ["allow_bot_to_play_for_me"]


class Player(models.Model):
    if TYPE_CHECKING:
        seat_set = RelatedManager["Seat"]()

    seat: Seat
    objects = PlayerManager()

    user = models.OneToOneField(
        auth.models.User,
        on_delete=models.CASCADE,
    )

    allow_bot_to_play_for_me = models.BooleanField(default=True)

    # TODO -- conceptually, this oughta be a OneToOneField, no?

    # On the other hand -- do I need this at all?  If our player is seated, then we can deduce his partner by seeing
    # who's sitting across from him.  But then if the partnership isn't seated, I'm outta luck.
    partner = models.ForeignKey("Player", null=True, blank=True, on_delete=models.SET_NULL)

    messages_for_me = GenericRelation(
        Message,
        related_query_name="player_recipient",
        content_type_field="recipient_content_type",
        object_id_field="recipient_object_id",
    )

    def libraryThing(self, *, hand: Hand) -> bridge.table.Player:
        """
        The returned object contains their hand *as dealt*, not necessarily their current holding.
        """

        seat = Seat.objects.get(player=self, table=hand.table)

        libHand = hand.libraryThing(seat)

        return bridge.table.Player(
            seat=seat.libraryThing,
            name=self.name,
            hand=libHand,
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

            table = self.current_table

            old_partner_pk = self.partner.pk
            Player.objects.filter(pk__in={self.pk, self.partner.pk}).update(partner=None)

            if table is not None and table.id is not None:
                table.delete()

        self._send_partnership_messages(action=SPLIT, old_partner_pk=old_partner_pk)

    @property
    def current_table(self) -> Table | None:
        if self.most_recent_seat is None:
            return None
        return self.most_recent_seat.table

    # TODO -- what I really want is *current_seat*.  What's the difference?  As long as we cannot have a player at two
    # tables at the same time, this should be OK.
    @cached_property
    def most_recent_seat(self) -> Seat | None:
        return Seat.objects.filter(player=self).order_by("-id").first()

    @property
    def hands_played(self) -> models.QuerySet:
        from .hand import Hand
        from .table import Table

        my_seats = Seat.objects.filter(player=self)
        my_tables = Table.objects.filter(seat__in=my_seats)
        return Hand.objects.filter(table__in=my_tables)

    def has_played_hand(self, hand: Hand) -> bool:
        return hand in self.hands_played.all()

    def hand_at_which_board_was_played(self, board: Board) -> Hand | None:
        from .hand import Hand
        from .table import Table

        return Hand.objects.filter(
            board=board,
            table__in=Table.objects.filter(
                pk__in=self.seat_set.values_list("table_id", flat=True).all()
            ).all(),
        ).first()

    def has_ever_seen_board(self, board: Board, hand: Hand | None = None) -> bool:
        if hand is None:
            hand = self.hand_at_which_board_was_played(board)
        return hand is not None

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

    @property
    def name_dir(self) -> str:
        direction = ""
        role = ""
        if self.most_recent_seat:
            direction = f" ({self.most_recent_seat.named_direction})"

            a: bridge.auction.Auction
            a = self.most_recent_seat.table.current_auction
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


admin.site.register(Player, PlayerAdmin)
