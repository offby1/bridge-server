from bridge.contract import Bid
from django.contrib import admin, auth
from django.db import models
from django.urls import reverse
from django.utils.html import format_html


class PlayerManager(models.Manager):
    def get_by_name(self, name):
        return self.get(user__username=name)


class Player(models.Model):
    objects = PlayerManager()

    user = models.OneToOneField(
        auth.models.User,
        on_delete=models.CASCADE,
    )

    looking_for_partner = models.BooleanField(default=False)

    @property
    def table(self):
        return Table.objects.filter(
            models.Q(north=self) | models.Q(east=self) | models.Q(south=self) | models.Q(west=self),
        ).first()

    @property
    def is_seated(self):
        return self.table is not None

    @property
    def name(self):
        return self.user.username

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


class TableException(Exception):
    pass


class Table(models.Model):
    north = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_north")
    east = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_east")
    south = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_south")
    west = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="table_west")

    DIRECTIONS = ["north", "east", "south", "west"]

    def players_by_direction(self):
        return {dir: getattr(self, dir) for dir in self.DIRECTIONS}

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:table-detail", kwargs=dict(pk=self.pk)),
            str(self),
        )

    # TODO -- can this be done with https://docs.djangoproject.com/en/5.0/ref/models/constraints/?
    def _check_seats_all_distinct(self):
        if len(set([self.north, self.east, self.west, self.south])) < 4:
            raise TableException("Yo cuz you can't sit in more than one seat at a table")

    def _check_no_player_is_already_seated(self):
        for _, p in self.players_by_direction().items():
            if p.is_seated:
                raise TableException(f"{p} is already seated")

    def _reset_fields(self):
        for _, p in self.players_by_direction().items():
            if p.looking_for_partner:
                p.looking_for_partner = False
                p.save()

    def save(self, *args, **kwargs):
        self._check_seats_all_distinct()
        self._check_no_player_is_already_seated()
        self._reset_fields()
        super().save(*args, **kwargs)

    def __str__(self):
        return ", ".join([f"{d}:{getattr(self, d)}" for d in self.DIRECTIONS])


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
