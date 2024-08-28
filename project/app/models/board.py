import more_itertools
from bridge.card import Card
from bridge.seat import Seat

# A "board" is a little tray with four slots, labeled "North", "East", "West", and "South".  The labels might be red, indicating that that pair is vulnerable; or not.
# https://en.wikipedia.org/wiki/Board_(bridge)
# One of the four slots says "dealer" next to it.
# In each slot are -- you guessed it -- 13 cards.  The board is thus a pre-dealt hand.
from django.db import models


class BoardManager(models.Manager):
    def create_with_deck(
        self,
        *,
        ns_vulnerable,
        ew_vulnerable,
        dealer,
        deck,
        table,
    ):
        def deserialize_hand(cards):
            return "".join([c.serialize() for c in cards])

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
            table=table,
        )


class Board(models.Model):
    objects = BoardManager()

    ns_vulnerable = models.BooleanField()
    ew_vulnerable = models.BooleanField()

    dealer = models.SmallIntegerField(db_comment="""corresponds to bridge library's "direction" """)

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

    def save(self, *args, **kwargs):
        assert isinstance(self.north_cards, str), f"Those bastards!! {self.north_cards=}"
        return super().save(*args, **kwargs)
