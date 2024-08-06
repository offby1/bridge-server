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
        seat = Seat.objects.filter(player=self).first()
        if seat is None:
            return None
        return seat.table

    @property
    def is_seated(self):
        return Seat.objects.filter(player=self).exists()

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


class TableManager(models.Manager):
    def get_nonfull(self):
        return self.annotate(num_seats=models.Count("seat")).filter(num_seats__lt=4)


class Table(models.Model):
    objects = TableManager()

    def players_by_direction(self):
        seats = self.seat_set.all()
        return {s.direction: s.player for s in seats}

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:table-detail", kwargs=dict(pk=self.pk)),
            str(self),
        )

    def __str__(self):
        return ", ".join([f"{d}: {p}" for d, p in self.players_by_direction().items()])


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
    player = models.OneToOneField(Player, null=True, on_delete=models.CASCADE)
    table = models.ForeignKey(Table, on_delete=models.CASCADE)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.player is not None:
            self.player.looking_for_partner = False
            self.player.save()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["direction", "player", "table"],
                name="why_do_I_gotta_name_these",
            ),
        ]


class Call(models.Model):
    seat = models.ForeignKey("Seat", on_delete=models.CASCADE)

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
