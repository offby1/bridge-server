from __future__ import annotations

import datetime
import logging
import pathlib
import subprocess
from typing import TYPE_CHECKING

import bridge.auction
import bridge.card
import bridge.seat
import bridge.table
from django.contrib import admin, auth
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django_eventstream import send_event  # type: ignore [import-untyped]
from django_extensions.db.models import TimeStampedModel  # type: ignore [import-untyped]
from faker import Faker

from .board import Board
from .common import attribute_names
from .message import Message
from .playaz import WireCharacterProvider
from .types import PK_from_str

if TYPE_CHECKING:
    from .hand import Hand
    from .types import PK

logger = logging.getLogger(__name__)


JOIN = "partnerup"
SPLIT = "splitsville"

MAX_BOT_PROCESSES = 40


class PlayerManager(models.Manager):
    @staticmethod
    def _find_unused_username(prefix=""):
        fake = Faker()
        Faker.seed(0)
        fake.add_provider(WireCharacterProvider)

        while True:
            # Ensure neither the prefixed, nor the unprefixed, version exists.
            unprefixed_candidate = fake.unique.playa().lower()
            candidates = [unprefixed_candidate, prefix + unprefixed_candidate]
            if not auth.models.User.objects.filter(username__in=candidates).exists():
                return candidates[-1]
            logger.debug("User named %s already exists; let's try another", " or ".join(candidates))

    def create_synthetic(self) -> Player:
        new_user = auth.models.User.objects.create_user(
            username=self._find_unused_username(prefix="synthetic_")
        )
        return Player.objects.create(synthetic=True, allow_bot_to_play_for_me=True, user=new_user)

    def get_from_user(self, user):
        return self.get(user=user)

    def get_by_name(self, name):
        return self.get(user__username=name)


class PlayerException(Exception):
    pass


class TooManyBots(PlayerException):
    pass


class PartnerException(PlayerException):
    pass


class Player(TimeStampedModel):
    display_name: str  # set by a view, from name_dir
    objects = PlayerManager()

    user = models.OneToOneField(
        auth.models.User,
        on_delete=models.CASCADE,
    )

    # TODO -- conceptually, this oughta be a OneToOneField, no?

    # On the other hand -- do I need this at all?  If our player is seated, then we can deduce his partner by seeing
    # who's sitting across from him.  But then if the partnership isn't seated, I'm outta luck.
    partner = models.ForeignKey["Player"](
        "Player", null=True, blank=True, on_delete=models.SET_NULL
    )

    # This is semi-redundant.  If it's True, there *must* be some seat whose player is me; we check this in our `save` method.
    # If it's False, anything goes -- if there are no such seats, then it's fine (I've never been seated); otherwise,
    # those seats are historical, and I've since left my last table, and not chosen a new one.

    # This gets set to True when someone creates a Seat instance whose player is us; it gets set to False when our
    # partnership splits up.
    currently_seated = models.BooleanField(default=False)
    allow_bot_to_play_for_me = models.BooleanField(default=False)
    synthetic = models.BooleanField(default=False)

    messages_for_me = GenericRelation(
        Message,
        related_query_name="player_recipient",
        content_type_field="recipient_content_type",
        object_id_field="recipient_object_id",
    )

    def _hands_played(self) -> models.QuerySet:
        from app.models import Hand

        hands = Hand.objects.all()

        expression = models.Q(pk__in=[])
        for direction in attribute_names:
            expression |= models.Q(**{direction: self})

        return hands.filter(expression)

    @cached_property
    def boards_played(self) -> models.QuerySet:
        return Board.objects.filter(id__in=self._hands_played().values_list("board", flat=True))

    def last_action(self) -> tuple[datetime.datetime, str]:
        rv = (self.created, "joined")
        if self.user.last_login and self.user.last_login > rv[0]:
            rv = (self.user.last_login, "logged in")
        if (h := self.hands_played.order_by("-id").first()) is not None:
            # TODO: somehow narrow stuff down to the most recent action that *we* took in this hand, as opposed to my
            # partner or opponents
            hand_last_action = h.last_action()
            if hand_last_action[0] > rv[0]:
                rv = hand_last_action

        return rv

    def unseat_me(self) -> None:
        with transaction.atomic():
            if (ch := self.current_hand()) is not None:
                if ch[0].abandoned_because is None:
                    ch[0].abandoned_because = f"{self.name} left"
                    ch[0].save()

            self.currently_seated = False
            self._control_bot()

    @property
    def event_channel_name(self):
        return f"system:player:{self.pk}"

    @staticmethod
    def player_pk_from_event_channel_name(cn: str) -> PK | None:
        pieces = cn.split("system:player:")
        if len(pieces) != 2:
            return None
        return PK_from_str(pieces[1])

    # https://cr.yp.to/daemontools/svc.html
    def _control_bot(self) -> None:
        service_directory = pathlib.Path("/service")
        if not service_directory.is_dir():
            logger.debug(f"Bailing out early because {service_directory=} is not a directory")
            return

        def run_in_slash_service(command: list[str]) -> None:
            subprocess.run(
                command,
                cwd=service_directory,
                check=False,
                capture_output=True,
            )

        def svc(flags: str) -> None:
            # No problem blocking here -- experience shows this doesn't take long
            run_in_slash_service(
                [
                    "svc",
                    flags,
                    str(self.pk),
                ],
            )

        if not self.allow_bot_to_play_for_me or not self.currently_seated:
            logger.info(
                f"{self.name=} {self.allow_bot_to_play_for_me=} {self.currently_seated=}; ensuring bot is stopped"
            )
            svc("-d")
            logger.info("Stopped bot for %s", self)
            return

        shell_script_text = """#!/bin/bash

# wrapper script for [daemontools](https://cr.yp.to/daemontools/)

set -euo pipefail

printf "%s %s %s "$(date -u +%FT%T%z) pid:$$ cwd:$(pwd)
exec /api-bot/.venv/bin/python /api-bot/apibot.py
    """
        run_dir = pathlib.Path("/service") / pathlib.Path(str(self.pk))
        run_file = run_dir / "run.notyet"
        run_file.parent.mkdir(parents=True, exist_ok=True)
        run_file.write_text(shell_script_text)
        run_file.chmod(0o755)
        run_file = run_file.rename(run_dir / "run")

        svc("-u")
        logger.info("Started bot for %s", self)

    def toggle_bot(self, desired_state: bool | None = None) -> None:
        with transaction.atomic():
            if desired_state is None:
                desired_state = not self.allow_bot_to_play_for_me

            if desired_state is True:
                c = Player.objects.filter(allow_bot_to_play_for_me=True).count()
                if c >= MAX_BOT_PROCESSES:
                    msg = f"There are already {c} bots; no bot for you"
                    raise TooManyBots(msg)

            self.allow_bot_to_play_for_me = desired_state
            self.save()
            self._control_bot()

    def save(self, *args, **kwargs) -> None:
        self._check_synthetic()
        super().save(*args, **kwargs)

    def _check_synthetic(self) -> None:
        if not self.pk:
            return
        original = Player.objects.get(pk=self.pk)
        if self.synthetic != original.synthetic:
            raise ValidationError("The 'synthetic' field cannot be changed.")

    def libraryThing(self) -> bridge.table.Player:
        tmp = self.current_hand()

        if tmp is None:
            msg = f"{self} is not seated, so cannot be converted to a bridge-library Player"
            raise PlayerException(msg)

        _, direction_name = tmp

        return bridge.table.Player(
            seat=bridge.seat.Seat(direction_name[0].upper()),
            name=self.name,
        )

    @property
    def looking_for_partner(self):
        return self.partner is None

    def _send_partnership_messages(self, *, action, old_partner_pk=None):
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
            self._send_partnership_messages(action=JOIN)

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

            old_partner_pk = self.partner.pk

            import app.models

            evictees = app.models.TournamentSignup.objects.filter(player__in={self, self.partner})
            logger.debug(
                "About to remove %s",
                ", ".join(
                    [
                        f"{su.player.name} from signups for t#{su.tournament.display_number}"
                        for su in evictees
                    ]
                ),
            )
            evictees.delete()

            self.partner.partner = None
            self.partner.unseat_me()
            self.partner.save(update_fields=["partner", "currently_seated"])

            self.partner = None
            self.unseat_me()
            self.save(update_fields=["partner", "currently_seated"])

        self._send_partnership_messages(action=SPLIT, old_partner_pk=old_partner_pk)

    def current_hand(self) -> tuple[Hand, str] | None:
        h: Hand
        direction_name: str

        for h in self._hands_played():
            if not h.is_complete:
                for direction_name in h.direction_names:
                    if getattr(h, direction_name) == self:
                        return h, direction_name

        return None

    def dealt_cards(self) -> list[bridge.card.Card]:
        tmp = self.current_hand()

        if tmp is None:
            msg = f"{self} is not seated, so has no cards"
            raise PlayerException(msg)

        h, direction_name = tmp

        return h.board.cards_for_direction_string(direction_name)

    @property
    def hands_played(self) -> models.QuerySet:
        return self._hands_played()

    def has_played_hand(self, hand: Hand) -> bool:
        return hand in self.hands_played.all()

    def hand_at_which_board_was_played(self, board: Board) -> Hand | None:
        from .hand import Hand

        qs = Hand.objects.filter(board=board).all()
        if qs.count() > 1:
            logger.critical("%s", f"Uh oh -- {self} played {board} more than once: {qs.all()}")
        return qs.first()

    def _boards_played(self) -> models.QuerySet:
        return Board.objects.filter(pk__in=self.hands_played.values_list("board", flat=True))

    def has_seen_board_at(self, board: Board, seat: bridge.seat.Seat) -> bool:
        return board in self._boards_played()

    @cached_property
    def name(self):
        return self.user.username

    def name_dir(self, *, hand: Hand) -> str:
        return f"{self.pk}:{self.as_link()}"

    def as_link(self, style=""):
        name = self.name
        if self.synthetic:
            name = format_html("<i>{}</i>", self.name)
        return format_html(
            "<a style='{}' href='{}'>{}</a>",
            style,
            reverse("app:player", kwargs={"pk": self.pk}),
            name,
        )

    def create_synthetic_partner(self) -> Player:
        with transaction.atomic():
            if self.partner is not None:
                return self.partner

            existing = Player.objects.filter(synthetic=True).filter(partner__isnull=True)
            if existing.exists():
                raise PartnerException(
                    f"There are already existing synths {[s.name for s in existing.all()]}"
                )
            new_player = Player.objects.create_synthetic()
            new_player.partner = self
            self.partner = new_player
            self.save()
            new_player.save()
            return self.partner

    def create_synthetic_opponents(self) -> list[Player]:
        with transaction.atomic():
            existing = (
                Player.objects.filter(synthetic=True)
                .filter(partner__isnull=False)
                .filter(currently_seated=False)
                .exclude(partner=self)
            )
            if existing.count() >= 2:
                raise PartnerException(
                    f"There are already at least two existing synths {[s.name for s in existing.all()]}"
                )
            rv: list[Player] = []

            while len(rv) < 2:
                rv.append(Player.objects.create_synthetic())

            rv[0].partner = rv[1]
            rv[1].partner = rv[0]
            for p in rv:
                p.save()

            return rv

    class Meta:
        ordering = ["user__username"]
        constraints = [
            models.CheckConstraint(  # type: ignore [call-arg]
                name="%(app_label)s_%(class)s_cant_be_own_partner",
                condition=models.Q(partner__isnull=True) | ~models.Q(partner_id=models.F("id")),
            ),
            models.CheckConstraint(
                name="synthetic_players_must_allow_bot_to_play_for_them",
                condition=models.Q(synthetic=False) | models.Q(allow_bot_to_play_for_me=True),
            ),  # type: ignore [call-arg]
        ]

    def __repr__(self) -> str:
        return f"modelPlayer{vars(self)}"

    def __str__(self):
        if self.synthetic:
            return f"🤖🤖{self.name}🤖🤖"
        return self.name


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ["name", "synthetic", "allow_bot_to_play_for_me", "currently_seated"]
    list_filter = ["currently_seated"]
