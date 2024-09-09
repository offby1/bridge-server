import logging
from typing import Any

import bridge.auction
import bridge.table
from django.contrib import admin, auth
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.urls import reverse
from django.utils.html import format_html
from django_eventstream import send_event  # type: ignore

from .message import Message
from .seat import Seat

logger = logging.getLogger(__name__)


JOIN = "partnerup"
SPLIT = "splitsville"


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
    seat: Any
    objects = PlayerManager()

    user = models.OneToOneField(
        auth.models.User,
        on_delete=models.CASCADE,
    )

    is_human = models.BooleanField(default=False)

    # TODO -- conceptually, this oughta be a OneToOneField, no?
    partner = models.ForeignKey("Player", null=True, blank=True, on_delete=models.SET_NULL)

    messages_for_me = GenericRelation(
        Message,
        related_query_name="player_recipient",
        content_type_field="recipient_content_type",
        object_id_field="recipient_object_id",
    )

    @property
    def libraryThing(self) -> bridge.table.Player:
        try:
            libHand = bridge.table.Hand(
                cards=self.seat.table.current_board.cards_for_direction(self.seat.direction),
            )
        except KeyError as e:
            msg = f"{self} just might not be seated at {self.table}"
            raise PlayerException(msg) from e

        return bridge.table.Player(
            seat=self.seat.libraryThing,
            name=self.name,
            hand=libHand,
        )

    @property
    def looking_for_partner(self):
        return self.partner is None

    def _send_partnershipt_messages(self, *, action, old_partner_pk=None):
        if action == JOIN:
            send_event(
                *Message.create_lobby_event_args(
                    from_player=self,
                    message=f"Partnered with {self.partner.name}",
                ),
            )

        # We always send two arrays, even though one is empty.  That's because I'm too stupid a JS programmer to deal
        # with missing attributes.
        data = {"split": [], "joined": []}

        if action == SPLIT:
            data["split"] = [old_partner_pk, self.pk]
        else:
            data["joined"] = [self.partner.pk, self.pk]

        channel = "partnerships"

        send_event(
            channel=channel,
            event_type="message",
            data=data,
        )

    def partner_with(self, other):
        with transaction.atomic():
            if self.partner not in (None, other):
                msg = f"Cannot partner with {other=} cuz I'm already partnered with {self.partner=}"
                raise PartnerException(
                    msg,
                )
            if other.partner not in (None, self):
                msg = f"Cannot partner {other=} with {self=} cuz they are already partnered with {other.partner=}"
                raise PartnerException(
                    msg,
                )

            self.partner = other
            other.partner = self

            self.save()
            other.save()
            self._send_partnershipt_messages(action=JOIN)

    def break_partnership(self):
        with transaction.atomic():
            if self.partner is None:
                msg = "Cannot break up with partner 'cuz we don't *have* a partner"
                raise PartnerException(
                    msg,
                )

            if self.partner.partner is None:
                msg = "Oh shit -- our partner doesn't have a partner"
                raise PartnerException(
                    msg,
                )

            table = self.table

            old_partner_pk = self.partner.pk
            Player.objects.filter(pk__in={self.pk, self.partner.pk}).update(partner=None)
            Seat.objects.filter(player__in={self, self.partner}).update(player=None)

            if table is not None:
                table.delete()

        self._send_partnershipt_messages(action=SPLIT, old_partner_pk=old_partner_pk)

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

    @property
    def name_dir(self):
        direction = ""
        if hasattr(self, "seat"):
            direction = f" ({self.seat.named_direction})"

            # TODO -- mark the dummy too, I guess?
            status = self.seat.table.current_auction.status

            if isinstance(status, bridge.auction.Contract):
                libPlayer = status.player

                if self.name == libPlayer.name:
                    return f"Declarer! {self.user.username}{direction}"

        return f"{self.user.username}{direction}"

    def as_link(self, style=""):
        return format_html(
            "<a style='{}' href='{}'>{}</a>",
            style,
            reverse("app:player", kwargs={"pk": self.pk}),
            str(self),
        )

    def _check_partner_table_consistency(self):
        # if we're seated, we must have a partner.
        seat = getattr(self, "seat", None)

        if seat is None:
            return

        if self.partner is None:
            msg = f"{self} is seated at {self.seat} but has no partner!!"
            raise PlayerException(msg)

    # TODO -- see if we can do this check in a constraint
    def save(self, *args, **kwargs):
        self._check_partner_table_consistency()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["user__username"]
        constraints = [
            models.CheckConstraint(  # type: ignore
                name="%(app_label)s_%(class)s_cant_be_own_partner",
                condition=models.Q(partner__isnull=True) | ~models.Q(partner_id=models.F("id")),
            ),
        ]

    def __str__(self):
        return f"{self.name} ({'human' if self.is_human else 'bot'})"


admin.site.register(Player)
