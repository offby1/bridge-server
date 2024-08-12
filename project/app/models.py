import bridge.seat
from bridge.contract import Bid
from django.contrib import admin, auth
from django.db import models, transaction
from django.urls import reverse
from django.utils.html import format_html


class PlayerManager(models.Manager):
    def get_by_name(self, name):
        return self.get(user__username=name)


class PlayerException(Exception):
    pass


class PartnerException(PlayerException):
    pass


class Player(models.Model):
    objects = PlayerManager()

    user = models.OneToOneField(
        auth.models.User,
        on_delete=models.CASCADE,
    )

    partner = models.ForeignKey("Player", null=True, blank=True, on_delete=models.SET_NULL)

    @property
    def looking_for_partner(self):
        return self.partner is None

    def partner_with(self, other):
        with transaction.atomic():
            if self.partner not in (None, other):
                raise PartnerException(
                    f"Cannot partner with {other=} cuz I'm already partnered with {self.partner=}",
                )
            if other.partner not in (None, self):
                raise PartnerException(
                    f"Cannot partner {other=} with {self=} cuz they are already partnered with {other.partner=}",
                )

            self.partner = other
            other.partner = self
            self.save()
            other.save()

    def break_partnership(self):
        with transaction.atomic():
            if self.partner is None:
                raise PartnerException(
                    "Cannot break up with partner 'cuz we don't *have* a partner",
                )

            if self.partner.partner is None:
                raise PartnerException(
                    "Oh shit -- our partner doesn't have a partner",
                )

            if self.partner is not None:
                self.partner.partner = None
                self.partner.save()
                self.partner = None
                self.save()

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
            str(self).title(),
        )

    def as_tuples(self):
        return [(SEAT_CHOICES[d], p) for d, p in self.players_by_direction().items()]

    def __str__(self):
        return ", ".join([f"{d}: {p}" for d, p in self.as_tuples()])


admin.site.register(Table)


SEAT_CHOICES = {v.value: k for k, v in bridge.seat.Seat.__members__.items()}


class SeatException(Exception):
    pass


class Seat(models.Model):
    direction = models.SmallIntegerField(
        choices=SEAT_CHOICES,
    )
    player = models.OneToOneField(Player, null=True, on_delete=models.CASCADE)
    table = models.ForeignKey(Table, on_delete=models.CASCADE)

    def partner_with(self, other):
        if self.player is None:
            raise SeatException(
                f"Cannot partner {self=} with {other=} because {self.player=} is None",
            )

        if other.player is None:
            raise SeatException(
                f"Cannot partner {self=} with {other=} because {other.player=} is None",
            )

        if self.player.partner is not None:
            raise SeatException(
                f"Cannot partner {self=} with {other=} because {self.player.partner=} is already partnered up",
            )
        if other.player.partner is not None:
            raise SeatException(
                f"Cannot partner {self=} with {other=} because {other.player.partner=} is already partnered up",
            )

        self.player.partner_with(other.player)

    def library_object_thingy(self):
        return bridge.seat.Seat(self.direction)

    def save(self, *args, **kwargs):
        lot = self.library_object_thingy()

        partner_direction = lot.partner()
        partner_seat = Seat.objects.filter(
            direction=partner_direction.value,
            table=self.table,
        ).first()

        if self.player is not None and partner_seat is not None and partner_seat.player is not None:
            self.partner_with(partner_seat)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{SEAT_CHOICES[self.direction]} at {self.table=}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "table"],
                name="no_more_than_one_player_per_table",
            ),
            models.UniqueConstraint(
                fields=["direction", "table"],
                name="no_more_than_four_directions_per_table",
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_direction_valid",
                condition=models.Q(direction__in=SEAT_CHOICES),
            ),
        ]


admin.site.register(Seat)


class Call(models.Model):
    # The "who"
    seat = models.ForeignKey("Seat", on_delete=models.CASCADE)

    @property
    def player(self):
        return self.seat.player

    # Now, the "what":
    # pass, bid, double, redouble

    serialized = models.CharField(
        max_length=10,
        db_comment="A short string with which we can create a bridge.contract.Call object",
    )

    def __str__(self):
        call = Bid.deserialize(self.serialized)
        return f"{self.player} ({self.seat.direction} at {self.seat.table}) says {self.serialized} which means {call}"


admin.site.register(Call)
