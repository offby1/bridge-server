from django.contrib import admin, auth
from django.db import models
from django.urls import reverse
from django.utils.html import format_html

# FWIW, https://docs.djangoproject.com/en/4.2/howto/custom-model-fields/#our-example-object demonstrates a Django model
# for a bridge hand.


class Table(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def empty_seats(self):
        all_seats = Seat.objects

        my_seats = all_seats.filter(table=self)

        return my_seats.filter(player__isnull=True)

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

    table = models.ForeignKey(Table, on_delete=models.CASCADE)

    def __str__(self):
        return f"Table {self.table} {self.direction}"

    def _check_direction(self):
        if self.direction not in "NESW":
            raise Exception(f"{self.direction=} is not in 'NESW'")

    def save(self, *args, **kwargs):
        # TODO -- shouldn't I be using "clean" or something?
        self._check_direction()
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
    table_played_at = models.ForeignKey("Table", on_delete=models.CASCADE)


admin.site.register(Hand)
