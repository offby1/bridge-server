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

    # TODO -- ensure this isn't True if we're seated at a table.
    looking_for_partner = models.BooleanField(default=False)

    @property
    def table(self):
        # TODO: I've probably noted this elsewhere, but we need to ensure that each player is associated with *at most one* table.
        return Table.objects.filter(
            models.Q(north=self) | models.Q(east=self) | models.Q(south=self) | models.Q(west=self),
        ).first()

    @property
    def is_seated(self):
        return self.table is not None

    @property
    def name(self):
        return self.user.username

    @classmethod
    def get_by_name(kls, name):
        return kls.objects.get(user__username=name)

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:player", kwargs=dict(pk=self.pk)),
            str(self),
        )

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return self.name


admin.site.register(Player)


class Table(models.Model):
    north = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_north")
    east = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_east")
    south = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_south")
    west = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_west")

    def players(self):
        return {dir: getattr(self, dir) for dir in ["north", "east", "south", "west"]}

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:table-detail", kwargs=dict(pk=self.pk)),
            str(self),
        )

    def __str__(self):
        return ", ".join([f"{d}:{getattr(self, d)}" for d in ["north", "east", "west", "south"]])


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
