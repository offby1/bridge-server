from django.contrib import admin, auth
from django.db import models, transaction
from django.urls import reverse
from django.utils.html import format_html

from .seat import Seat


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

    def as_link(self, style=""):
        return format_html(
            "<a style='{}' href='{}'>{}</a>",
            style,
            reverse("app:player", kwargs=dict(pk=self.pk)),
            str(self),
        )

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return self.name


admin.site.register(Player)
