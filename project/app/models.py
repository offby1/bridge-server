import itertools
import random

import bridge.card
import more_itertools
from django.contrib import admin, auth
from django.db import models
from django.urls import reverse
from django.utils.html import format_html

# FWIW, https://docs.djangoproject.com/en/4.2/howto/custom-model-fields/#our-example-object demonstrates a Django model
# for a bridge hand.


class Table(models.Model):
    name = models.CharField(max_length=100, unique=True)

    @property
    def my_seats(self):
        return Seat.objects.filter(table=self)

    def empty_seats(self):
        return self.my_seats.filter(player__isnull=True)

    def ordered_seats(self):
        for dir in "NESW":
            yield self.my_seats.get(direction=dir)

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:table-detail", kwargs=dict(pk=self.pk)),
            str(self),
        )

    @classmethod
    def non_full_table(kls):
        # This seems dumb
        for t in kls.objects.all():
            if t.empty_seats().exists():
                return t

    def __str__(self):
        return self.name


admin.site.register(Table)


class Seat(models.Model):
    NORTH = "N"
    EAST = "E"
    SOUTH = "S"
    WEST = "W"

    DIRECTION_CHOICES = {
        NORTH: "North",
        EAST: "East",
        SOUTH: "South",
        WEST: "West",
    }

    direction = models.CharField(
        max_length=1,
        choices=DIRECTION_CHOICES,
    )

    @classmethod
    def create_for_table(kls, t):
        for direction in kls.DIRECTION_CHOICES.keys():
            kls.objects.create(table=t, direction=direction)

    cards = models.CharField(
        max_length=26,
        blank=True,
        default="",
        db_comment="String of even length; each pair of characters is like ♧2",
    )
    table = models.ForeignKey(Table, on_delete=models.CASCADE)

    def __str__(self):
        return f"Table {self.table} {self.direction}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "table",
                    "direction",
                ],
                name="composite_primary_key",
            ),
        ]


class Player(models.Model):
    user = models.OneToOneField(
        auth.models.User,
        on_delete=models.CASCADE,
    )
    seat = models.OneToOneField(
        "Seat",
        blank=True,
        null=True,
        db_comment="If NULL, then I'm in the lobby",
        on_delete=models.CASCADE,
    )

    @property
    def name(self):
        return self.user.username

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:player", kwargs=dict(pk=self.pk)),
            str(self),
        )

    def __str__(self):
        if self.seat is None:
            where = "in the lobby"
        else:
            where = f"at {self.seat}"
        return f"{self.name}, {where}"


admin.site.register(Player)


class Hand(models.Model):
    """A hand as dealt, as opposed to a hand currently being played.  IOW, this hand always has 52 cards distributed among four seats."""

    table_played_at = models.ForeignKey("Table", on_delete=models.CASCADE)

    def deal(self):
        if self.table_played_at.empty_seats().exists():
            raise Exception("Cannot deal to a table with empty seats")
        deck = bridge.card.Card.deck()
        random.shuffle(deck)

        for seat in self.table_played_at.seat_set.all():
            seat.cards = ""

        # TODO -- order the seats?  Only matters if we somehow make the shuffled deck visible before dealing; otherwise
        # nobody cares how we dealt, as long as it's random
        for hand, seat in zip(
            more_itertools.distribute(4, deck),
            self.table_played_at.seat_set.all(),
        ):
            seat.cards = "".join([str(card) for card in sorted(hand)])
            seat.save()


admin.site.register(Hand)
