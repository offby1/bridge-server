import logging

from django.contrib import admin, auth
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.urls import reverse
from django.utils.html import format_html
from django_eventstream import send_event

from .message import Message
from .seat import Seat

logger = logging.getLogger(__name__)


class PlayerManager(models.Manager):
    def get_from_user(self, user):
        return self.get(user=user)

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

    # TODO -- conceptually, this oughta be a OneToOneField, no?
    partner = models.ForeignKey("Player", null=True, blank=True, on_delete=models.SET_NULL)

    messages_for_me = GenericRelation(
        Message,
        related_query_name="player_recipient",
        content_type_field="recipient_content_type",
        object_id_field="recipient_object_id",
    )

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

            send_event(
                *Message.create_lobby_event_args(
                    from_player=self,
                    message=f"Partnered with {self.partner.name}",
                ),
            )

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

            send_event(
                *Message.create_lobby_event_args(
                    from_player=self,
                    message=f"Splitsville with {self.partner.name}",
                ),
            )

            seat_pks = set()
            for player in (self, self.partner):
                if s := getattr(player, "seat", None):
                    seat_pks.add(s.pk)

            Seat.objects.filter(pk__in=seat_pks).update(player=None)
            Player.objects.filter(pk__in={self.pk, self.partner.pk}).update(partner=None)

    @property
    def table(self):
        if getattr(self, "seat", None) is None:
            return None
        return self.seat.table

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

    def _check_partner_table_consistency(self):
        # if we're seated, we must have a partner.
        seat = getattr(self, "seat", None)

        if seat is None:
            return

        if self.partner is None:
            raise PlayerException(f"{self} is seated at {self.seat} but has no partner!!")

    # TODO -- see if we can do this check in a constraint
    def save(self, *args, **kwargs):
        self._check_partner_table_consistency()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["user__username"]
        constraints = [
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_cant_be_own_partner",
                condition=models.Q(partner__isnull=True) | ~models.Q(partner_id=models.F("id")),
            ),
        ]

    def __str__(self):
        return self.name


admin.site.register(Player)
