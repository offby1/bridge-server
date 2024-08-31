import more_itertools
from bridge.card import Card
from bridge.seat import Seat
from django.contrib import admin

# A "board" is a little tray with four slots, labeled "North", "East", "West", and "South".  The labels might be red, indicating that that pair is vulnerable; or not.
# https://en.wikipedia.org/wiki/Board_(bridge)
# One of the four slots says "dealer" next to it.
# In each slot are -- you guessed it -- 13 cards.  The board is thus a pre-dealt hand.
from django.db import models

from . import SEAT_CHOICES


class BoardManager(models.Manager):
    def create_from_deck_and_board_number(self, *, deck, board_number):
        board_number = board_number % 16

        # https://en.wikipedia.org/wiki/Board_(bridge)#Set_of_boards
        dealer = (board_number - 1) % 4 + 1
        only_ns_vuln = board_number in (2, 5, 12, 15)
        only_ew_vuln = board_number in (3, 6, 9, 16)
        all_vuln = board_number in (4, 7, 10, 13)
        kwargs = {
            "ns_vulnerable": only_ns_vuln or all_vuln,
            "ew_vulnerable": only_ew_vuln or all_vuln,
            "dealer": dealer,
            "deck": deck,
        }
        return self.create_with_deck(**kwargs)

    def create_with_deck(
        self,
        *,
        ns_vulnerable,
        ew_vulnerable,
        dealer,
        deck,
    ):
        def deserialize_hand(cards):
            # sorted only so that they look purty in the Admin site.
            return "".join([c.serialize() for c in sorted(cards)])

        north_cards = deserialize_hand(deck[0:13])
        east_cards = deserialize_hand(deck[13:26])
        south_cards = deserialize_hand(deck[26:39])
        west_cards = deserialize_hand(deck[39:52])

        return self.create(
            ns_vulnerable=ns_vulnerable,
            ew_vulnerable=ew_vulnerable,
            dealer=dealer,
            north_cards=north_cards,
            east_cards=east_cards,
            south_cards=south_cards,
            west_cards=west_cards,
        )


class Board(models.Model):
    objects = BoardManager()

    ns_vulnerable = models.BooleanField()
    ew_vulnerable = models.BooleanField()

    dealer = models.SmallIntegerField(db_comment="""corresponds to bridge library's "direction" """)  # type: ignore

    @property
    def fancy_dealer(self):
        return SEAT_CHOICES[self.dealer]

    @property
    def hand_strings_by_direction(self):
        return {
            Seat.NORTH.value: self.north_cards,
            Seat.EAST.value: self.east_cards,
            Seat.SOUTH.value: self.south_cards,
            Seat.WEST.value: self.west_cards,
        }

    def cards_for_direction(self, direction_integer):
        card_string = self.hand_strings_by_direction[direction_integer]
        return [Card.deserialize(c) for c in more_itertools.chunked(card_string, 2)]

    north_cards = models.CharField(max_length=26)
    east_cards = models.CharField(max_length=26)
    south_cards = models.CharField(max_length=26)
    west_cards = models.CharField(max_length=26)

    def __str__(self):
        if self.ns_vulnerable and self.ew_vulnerable:
            vuln = "Both sides"
        elif not self.ns_vulnerable and not self.ew_vulnerable:
            vuln = "Neither side"
        elif self.ns_vulnerable:
            vuln = "North/South"
        else:
            vuln = "East/West"

        return f"Board #{self.id}, {vuln} vulnerable, dealt by {self.fancy_dealer}"

    def save(self, *args, **kwargs):
        assert isinstance(self.north_cards, str), f"Those bastards!! {self.north_cards=}"
        return super().save(*args, **kwargs)


admin.site.register(Board)
