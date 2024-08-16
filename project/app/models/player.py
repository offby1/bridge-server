import logging

from django.contrib import admin, auth
from django.db import models, transaction
from django.urls import reverse
from django.utils.html import format_html
from django_eventstream import send_event

from .lobby import send_lobby_message
from .seat import Seat

logger = logging.getLogger(__name__)


def send_player_message(*, from_player, message, recipient_pk):
    recipient = Player.objects.get(pk=recipient_pk)
    obj = PlayerMessage.objects.create(
        from_player=from_player,
        message=message,
        recipient=recipient,
    )

    channel_name = "player:" + "_".join([str(pk) for pk in sorted([from_player.pk, recipient_pk])])
    send_event(
        channel_name,
        "message",
        {
            "who": from_player.user.username,
            "what": message,
            "when": obj.timestamp,
        },
    )


class PlayerMessage(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    from_player = models.ForeignKey("Player", on_delete=models.CASCADE, related_name="sent_message")
    message = models.TextField(max_length=128)
    recipient = models.ForeignKey(
        "Player",
        on_delete=models.CASCADE,
        related_name="received_message",
    )


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
            send_lobby_message(from_player=self, message=f"Partnered with {self.partner.name}")

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
                send_lobby_message(
                    from_player=self,
                    message=f"Splitsville with {self.partner.name}",
                )

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
