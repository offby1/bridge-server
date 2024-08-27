import random

from bridge.card import Card
from django.contrib import admin
from django.db import models, transaction
from django.urls import reverse
from django.utils.html import format_html

from . import SEAT_CHOICES
from .board import Board
from .seat import Seat


class TableException(Exception):
    pass


class TableManager(models.Manager):
    def get_nonfull(self):
        return self.annotate(num_seats=models.Count("seat")).filter(num_seats__lt=4)

    def create_with_two_partnerships(self, p1, p2):
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

        # TODO -- choose vulnerabilty and dealer sensibly
        deck = Card.deck()
        random.shuffle(deck)

        print(f"{deck=}")
        Board.objects.create_with_deck(
            ns_vulnerable=False,
            ew_vulnerable=False,
            dealer=0,
            deck=deck,
            table=t,
        )

        return t


# What, no fields?  Well, Django supplies a primary key for us; and more importantly, it will put a "seat_set" attribute
# onto each instance.
class Table(models.Model):
    objects = TableManager()

    @property
    def handrecords(self):
        return self.handrecord_set.order_by("id")

    @property
    def current_handrecord(self):
        return self.handrecord_set.order_by("-id").first()

    @property
    def dealer(self):
        return self.current_board.dealer

    def cards_by_player(self):
        rv = {}
        board = self.current_board
        if board is None:
            return rv
        for s in self.seat_set.all():
            if s.player is not None:
                rv[s.player] = board.cards_for_direction(s.direction)

        return rv

    # TODO -- find the newest one, not the "first" one
    @property
    def current_board(self):
        return self.board_set.first()

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
