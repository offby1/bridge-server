from __future__ import annotations

import datetime
import logging
import os
import pathlib
import subprocess
from typing import TYPE_CHECKING

import more_itertools

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
    import app.models

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

    def create_synthetic(self) -> Player:
        new_user = auth.models.User.objects.create_user(
            username=self._find_unused_username(prefix="_")
        )
        return Player.objects.create(synthetic=True, allow_bot_to_play_for_me=True, user=new_user)

    def get_or_create_synthetic(self, **exclude_kwargs) -> tuple[Player, bool]:
        existing = (
            Player.objects.filter(synthetic=True, partner__isnull=True)
            .exclude(**exclude_kwargs)
            .first()
        )
        if existing is not None:
            return existing, False

        return self.create_synthetic(), True

    def ensure_eight_players_signed_up(self, *, tournament: app.models.Tournament) -> None:
        with transaction.atomic():
            the_eight = [
                player for player in self.filter(tournamentsignup__tournament=tournament)[0:8]
            ]

            while len(the_eight) < 8:
                p, created = self.get_or_create_synthetic(pk__in=[p.pk for p in the_eight])
                logger.info("%s %s", "created" if created else "reused", p)
                the_eight.append(p)

            # now pair 'em up and sign 'em up
            unpartnered = [p for p in the_eight if p.partner is None]

            for chunk in more_itertools.chunked(unpartnered, 2):
                if len(chunk) == 2:
                    p1, p2 = chunk
                    p1.partner_with(p2)

            for p in the_eight:
                tournament.sign_up_player_and_partner(p)

    def get_from_user(self, user):
        return self.get(user=user)

    def get_by_name(self, name):
        return self.get(user__username=name)

    def currently_seated(self) -> models.QuerySet:
        seated_pks = set([p.pk for p in self.all() if p.currently_seated])
        return self.filter(pk__in=seated_pks)


class PlayerException(Exception):
    pass


class TooManyBots(PlayerException):
    pass


class PartnerException(PlayerException):
    pass


# fmt:off

# fmt:on
class Player(TimeStampedModel):
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

    allow_bot_to_play_for_me = models.BooleanField(default=False)
    synthetic = models.BooleanField(default=False)

    messages_for_me = GenericRelation(
        Message,
        related_query_name="player_recipient",
        content_type_field="recipient_content_type",
        object_id_field="recipient_object_id",
    )

    # *all* hands to which we've ever been assigned, regardless of whether they're complete or abandoned
    @property
    def hands_played(self) -> models.QuerySet:
        from app.models import Hand

        hands = Hand.objects.all()

        expression = models.Q(pk__in=[])
        for direction in attribute_names:
            expression |= models.Q(**{direction: self})

        return hands.filter(expression)

    @property
    def boards_played(self) -> models.QuerySet:
        return Board.objects.filter(pk__in=self.hands_played)

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

    def unseat_partnership(self, reason: str | None = None) -> None:
        with transaction.atomic():
            for p in (self, getattr(self, "partner")):
                if p is not None and p.currently_seated:
                    p.unseat_me(reason=reason)
        if reason is not None and self.partner is not None:
            channel = Message.channel_name_from_player_pks(self.pk, self.partner.pk)
            send_event(
                channel=channel,
                event_type="message",
                data=reason,
            )

    def unseat_me(self, reason: str | None = None) -> None:
        # TODO -- refactor this with "current_hand"
        logger.info("Unseating %s because %s", self.name, reason)
        with transaction.atomic():
            h: Hand
            direction_name: str

            for h in self.hands_played.filter(abandoned_because__isnull=True):
                if not h.is_complete:
                    for direction_name in h.direction_names:
                        if getattr(h, direction_name) == self:
                            h.abandoned_because = reason or f"{self.name} left"
                            h.save()
                            break
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
        # do nothing when run from a unit test, so as to reduce the noise in the log output.
        if os.environ.get("PYTEST_VERSION") is not None:
            return

        service_directory = pathlib.Path("/service")
        if not service_directory.is_dir():
            return

        def svc(flags: str) -> None:
            logger.info("'svc %s' for %s's bot (%r)", flags, self.name, self.pk)

            # No problem blocking here -- experience shows this doesn't take long
            proc = subprocess.run(
                [
                    "svc",
                    flags,
                    str(self.pk),
                ],
                cwd=service_directory,
                check=False,
                capture_output=True,
            )
            if proc.stderr:
                logger.warning("%s", proc.stderr)

        run_dir = pathlib.Path("/service") / pathlib.Path(str(self.pk))

        if not (self.allow_bot_to_play_for_me and self.currently_seated):
            try:
                (run_dir / "down").touch()
            except FileNotFoundError:
                pass
            svc("-d")
            return

        shell_script_text = """#!/bin/bash

# wrapper script for [daemontools](https://cr.yp.to/daemontools/)

set -euo pipefail

printf "%s %s %s "$(date -u +%FT%T%z) pid:$$ cwd:$(pwd)
exec /api-bot/.venv/bin/python /api-bot/apibot.py
    """
        run_file = run_dir / "run.notyet"
        run_file.parent.mkdir(parents=True, exist_ok=True)
        run_file.write_text(shell_script_text)
        run_file.chmod(0o755)
        run_file = run_file.rename(run_dir / "run")

        (run_dir / "down").unlink(missing_ok=True)
        svc("-u")

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

    def save(self, *args, **kwargs) -> None:
        self._check_synthetic()
        super().save(*args, **kwargs)
        self._control_bot()

    def _check_synthetic(self) -> None:
        if not self.pk:
            return
        original = Player.objects.get(pk=self.pk)
        if self.synthetic != original.synthetic:
            raise ValidationError("The 'synthetic' field cannot be changed.")

    def libraryThing(self) -> bridge.table.Player:
        direction_name = self.current_direction()

        if direction_name is None:
            msg = f"{self} is not seated, so cannot be converted to a bridge-library Player"
            raise PlayerException(msg)

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
                msg = f"Cannot partner with {other.name=} cuz I'm already partnered with {self.partner.name=}"
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
            self.partner.save(update_fields=["partner"])

            self.partner = None
            self.unseat_me()
            self.save(update_fields=["partner"])

        self._send_partnership_messages(action=SPLIT, old_partner_pk=old_partner_pk)

    @property
    def currently_seated(self) -> bool:
        return self.current_hand_and_direction() is not None

    def current_hand_and_direction(self) -> tuple[Hand, str] | None:
        h: Hand
        direction_name: str

        for h in self.hands_played:
            if not h.is_complete and h.abandoned_because is None:
                for direction_name in h.direction_names:
                    if getattr(h, direction_name) == self:
                        return h, direction_name

        return None

    def current_hand(self) -> Hand | None:
        ch = self.current_hand_and_direction()
        if ch is None:
            return None
        return ch[0]

    def current_direction(self) -> str | None:
        ch = self.current_hand_and_direction()
        if ch is None:
            return None
        return ch[1]

    def dealt_cards(self) -> list[bridge.card.Card]:
        ch = self.current_hand_and_direction()

        if ch is None:
            msg = f"{self} is not seated, so has no cards"
            raise PlayerException(msg)

        current_hand, direction_name = ch
        return current_hand.board.cards_for_direction_string(direction_name)

    def has_played_hand(self, hand: Hand) -> bool:
        return hand in self.hands_played.all()

    def hand_at_which_we_played_board(self, board: Board) -> Hand | None:
        from .hand import Hand

        expression = models.Q(pk__in=[])
        for direction in attribute_names:
            expression |= models.Q(**{direction: self.pk})

        qs = Hand.objects.filter(board=board).filter(expression)
        assert qs.count() < 2
        return qs.first()

    def has_seen_board_at(self, board: Board, seat: bridge.seat.Seat) -> bool:
        return board in self.boards_played.all()

    @cached_property
    def name(self):
        return self.user.username

    def display_name(self) -> str:
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
                    f"There are already existing, unpartnered synths {[s.name for s in existing.all()]}"
                )
            new_player = Player.objects.create_synthetic()
            new_player.partner = self
            self.partner = new_player
            self.save()
            new_player.save()
            return self.partner

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
        return self.name


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ["name", "synthetic", "allow_bot_to_play_for_me"]
    list_display = ["name", "synthetic", "allow_bot_to_play_for_me"]
