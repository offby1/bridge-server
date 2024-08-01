from bridge.contract import Bid
from django.contrib import admin, auth
from django.db import models
from django.urls import reverse
from django.utils.html import format_html


class Player(models.Model):
    user = models.OneToOneField(
        auth.models.User,
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
        return f"{self.name}, at some location I have yet to determine, TODO:"


admin.site.register(Player)


class Table(models.Model):
    north = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_north")
    east = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_east")
    south = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_south")
    west = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_west")

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:table-detail", kwargs=dict(pk=self.pk)),
            str(self),
        )

    # TODO -- constrain the four users to be different from each other -- i.e., nobody can take up more than one seat.

    # TODO -- ensure that the same set of four users cannot make a new table, if there already is a table with the four
    # of them that's still somehow "active"


admin.site.register(Table)


class Call(models.Model):
    # First, the "who"
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
    table = models.ForeignKey(Table, on_delete=models.CASCADE)

    @property
    def player(self):
        return getattr(self.table, self.DIRECTION_CHOICES[self.direction].lower())

    # Now, the "what":
    # pass, bid, double, redouble

    serialized = models.CharField(
        max_length=10,
        db_comment="A short string with which we can create a bridge.contract.Call object",
    )

    def __str__(self):
        call = Bid.deserialize(self.serialized)
        return f"{self.direction} at {self.table} says {self.serialized} which means {call}"


admin.site.register(Call)
