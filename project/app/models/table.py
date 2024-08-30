import random

from bridge.auction import Auction
from bridge.card import Card
from django.contrib import admin
from django.db import models, transaction
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html

from . import SEAT_CHOICES
from .board import Board
from .handrecord import HandRecord
from .seat import Seat


class TableException(Exception):
    pass


class TableManager(models.Manager):
    def get_nonfull(self):
        return self.annotate(num_seats=models.Count("seat")).filter(num_seats__lt=4)

    def create_with_two_partnerships(self, p1, p2):
        first_table = not self.exists()
        t = self.create()
        try:
            with transaction.atomic():
                for seat, player in zip(SEAT_CHOICES, (p1, p2, p1.partner, p2.partner)):
                    Seat.objects.create(
                        direction=seat,
                        player=player,
                        table=t,
                    )
        except Exception as e:
            raise TableException from e

        deck = Card.deck()

        # Just for testing, the first board will give each player a single 13-card suit
        if first_table:
            pass
        else:
            random.shuffle(deck)

        b = Board.objects.create_from_deck_and_board_number(
            board_number=Board.objects.count() + 1,
            deck=deck,
        )

        HandRecord.objects.create(board=b, table=t)
        return t


# What, no fields?  Well, Django supplies a primary key for us; and more importantly, it will put a "seat_set" attribute
# onto each instance.
class Table(models.Model):
    objects = TableManager()

    @property
    def handrecords(self):
        return self.handrecord_set.order_by("id")

    @cached_property
    def current_auction(self):
        rv = Auction(table=self, dealer=self.board.wtf.who_dealt)
        for player_int, call in self.current_handrecord.annotated_calls:
            rv.append_located_call(player_int, call)
        return rv

    @property
    def current_handrecord(self):
        return self.handrecord_set.order_by("-id").first()

    @property
    def dealer(self):
        return self.current_board.dealer

    def cards_by_player(self) -> dict[Seat, list[Card]]:
        rv = {}
        board = self.current_board
        if board is None:
            return rv
        for s in self.seat_set.all():
            if s.player is not None:
                rv[s] = board.cards_for_direction(s.direction)

        return rv

    @property
    def current_board(self):
        return self.current_handrecord.board

    def players_by_direction(self):
        seats = self.seat_set.all()
        return {s.direction: s.player for s in seats}

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:table-detail", kwargs=dict(pk=self.pk)),
            str(self),
        )

    def as_tuples(self):
        return [(SEAT_CHOICES[d], p) for d, p in self.players_by_direction().items()]

    def is_empty(self):
        for p in self.players_by_direction().values():
            if p is not None:
                return False

        return True

    def is_full(self):
        for p in self.players_by_direction().values():
            if p is None:
                return False

        return True

    def go_away_if_empty(self):
        if self.is_empty():
            self.delete()

    def __str__(self):
        playaz = ", ".join([f"{d}: {p}" for d, p in self.as_tuples()])
        return f"Table {self.id} ({playaz})"


admin.site.register(Table)
