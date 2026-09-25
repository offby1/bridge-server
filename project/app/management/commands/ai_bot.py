"""Plays every allow_bot_to_play_for_me seat.

Claude decides the call or play (see app.ai_bot's decide_call()/decide_play()),
falling back to the same dumb heuristics cheating_bot.py used to whenever Claude
isn't available: no API key configured, the AI_BOT_DISABLED kill switch (see
docs/ai-bot-cost-controls-plan.md), or the API call itself fails.

How a decision gets applied differs by seat:

- A synthetic (bot-created) Player -- a placeholder made by
  Player.create_synthetic_partner() to fill out a table -- is driven over HTTP, the
  way any other third-party client would (see app/reference_client.py): log in as
  that Player, GET /serialized/hand/<pk>/, POST to /call/ or /play/. Since nobody
  else ever logs into a synthetic account, this sets its own (random, per-run)
  password on one the first time it needs to act for it, purely so it can log in --
  game decisions and state changes never go through the ORM for these seats.
- A real human's own seat, delegated via allow_bot_to_play_for_me, is acted on
  directly through the ORM (hand.add_call()/add_play_from_model_player()), the way
  cheating_bot.py used to: resetting a real person's password to log in as them,
  the way the synthetic path does, isn't something this can do.

See docs/ai-bot-plan.md.
"""

from __future__ import annotations

import datetime
import logging
import os
import secrets
import time

import anthropic
import app.ai_bot as ai_bot
import app.models
import django.db.models
import django.utils.timezone
from app.reference_client import BridgeClient, BridgeClientError
from django.core.management.base import BaseCommand

from bridge.seat import Seat
from bridge.xscript import HandTranscript

logger = logging.getLogger(__name__)


def get_next_hand(logger: logging.Logger | None = None) -> app.models.Hand | None:
    """The oldest playable hand whose current seat is bot-controlled."""
    if logger is None:
        logger = logging.getLogger(__name__)

    expression = django.db.models.Q(pk__in=[])
    for direction in app.models.common.attribute_names:
        expression |= django.db.models.Q(**{f"{direction}__allow_bot_to_play_for_me": True})

    # TODO -- this isn't quite right. What we *really* want is to consider only those hands for whom the current seat is
    # controlled by a bot.  But the below sometimes gets us a hand whose current seat is controlled by a human, and that
    # basically prevents us from doing any other work.
    all_hands_with_bots = (
        app.models.Hand.objects.prepop()
        .filter(
            expression,
            is_complete=False,
            abandoned_because__isnull=True,
            board__tournament__completed_at__isnull=True,
            board__tournament__play_completion_deadline__gt=django.utils.timezone.now(),
        )
        .order_by("last_action_time")
    )

    # "manually" find the oldest hand whose current seat is controlled by the bot.  ideally we'd have the database do
    # this for us, rather than doing it here in Python; but it's not clear if that's possible.
    h: app.models.Hand
    for h in all_hands_with_bots:
        s = h.next_seat_to_call or h.next_seat_to_play

        if s is None:
            continue
        player = h.player_who_controls_seat(s, right_this_second=False)
        if not player.allow_bot_to_play_for_me:
            continue
        return h

    return None


def wait_for_tempo(hand_to_play: app.models.Hand) -> None:
    tempo = datetime.timedelta(seconds=hand_to_play.board.tournament.tempo_seconds)
    wait_until = hand_to_play.last_action_time + tempo
    now = django.utils.timezone.now()
    sleepy_time = max(datetime.timedelta(seconds=0), wait_until - now)
    time.sleep(sleepy_time.total_seconds())


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args, **options) -> None:
        base_url = os.environ.get("BRIDGE_BASE_URL", "http://localhost:9000")
        ai_client = ai_bot.client_if_enabled()
        logger.info(
            "ai_bot starting against %s; Claude is %s",
            base_url,
            "enabled" if ai_client is not None else "disabled -- using the dumb heuristics",
        )

        clients: dict[int, BridgeClient] = {}

        while True:
            if not self.process_one(base_url, clients, ai_client):
                time.sleep(1)

    def process_one(
        self,
        base_url: str,
        clients: dict[int, BridgeClient],
        ai_client: anthropic.Anthropic | None,
    ) -> bool:
        """Find and act on one bot-controlled seat's turn, if there is one.

        Split out from `handle()`'s infinite loop so tests can call it directly, a
        bounded number of times, instead of looping forever.
        """
        hand = get_next_hand(logger=logger)
        if hand is None:
            return False

        try:
            self._act(hand, base_url, clients, ai_client)
        except BridgeClientError as e:
            # Could be a genuine race (the turn moved on between our read and our
            # write) or something more persistently wrong. Either way, hammering
            # the same failing request with no delay is worse than a human
            # noticing a stalled bot a second later -- so this is *not* reported
            # as "there was work to do": the caller's own backoff applies, same
            # as when there's nothing to act on at all.
            logger.warning(
                "hand %s (%s, %s): %s",
                hand.pk,
                hand.board,
                hand.board.tournament,
                e,
            )
            return False

        return True

    def _xscript_for_seat(
        self,
        hand: app.models.Hand,
        player: app.models.Player,
        base_url: str,
        clients: dict[int, BridgeClient],
    ) -> tuple[HandTranscript, BridgeClient | None]:
        """The seat's own view of the hand -- over HTTP for a synthetic player (see
        module docstring), straight from the ORM for a real one, whose own cards
        are always visible to the process serving them anyway.

        Returns the client too, so the caller knows (by its presence) how to apply
        whatever decision it makes.
        """
        if player.synthetic:
            client = self._client_for(player, base_url, clients)
            return HandTranscript.from_python(client.hand(hand.pk)["xscript"]), client
        return hand.get_xscript(), None

    def _act(
        self,
        hand: app.models.Hand,
        base_url: str,
        clients: dict[int, BridgeClient],
        ai_client: anthropic.Anthropic | None,
    ) -> None:
        if (player := hand.player_who_may_call) is not None:
            call_seat = Seat(hand.direction_letters_by_player[player])
            logger.info("hand %s: %s (%s) may call", hand.pk, call_seat, player.name)
            xscript, client = self._xscript_for_seat(hand, player, base_url, clients)

            call, reason = ai_bot.decide_call(ai_client, xscript, call_seat)
            # Waiting *here* -- after deciding, right before the write -- rather than
            # before any of the above means an API round-trip (often longer than
            # tempo_seconds on its own) counts *as* the wait instead of stacking on
            # top of a full tempo_seconds sleep. Only tops up whatever's left.
            wait_for_tempo(hand)
            if client is not None:
                client.call(call.serialize(), explanation=call.explanation)
            else:
                hand.add_call(call=call)
            logger.info("hand %s: %s: %s (%s)", hand.pk, call_seat, call, reason)
            return

        play_seat = hand.next_seat_to_play
        if play_seat is None:
            logger.error("hand %s has a bot up but nobody may call or play", hand.pk)
            return

        player = hand.player_who_controls_seat(play_seat, right_this_second=True)
        logger.info("hand %s: %s (%s) may play", hand.pk, play_seat, player.name)
        xscript, client = self._xscript_for_seat(hand, player, base_url, clients)

        my_hand = xscript.dealt_cards_by_seat[play_seat]
        assert my_hand is not None, (
            f"{play_seat}'s own cards must be visible to whoever's playing them"
        )
        already_played = {p.card for p in xscript.plays() if p.seat == play_seat}
        legal = xscript.legal_cards(some_cards=[c for c in my_hand if c not in already_played])

        card, reason = ai_bot.decide_play(ai_client, xscript, play_seat, legal)
        wait_for_tempo(hand)
        if client is not None:
            client.play(str(card))
        else:
            hand.add_play_from_model_player(player=player, card=card)
        logger.info("hand %s: %s: plays %s (%s)", hand.pk, play_seat, card, reason)

    def _client_for(
        self,
        player: app.models.Player,
        base_url: str,
        clients: dict[int, BridgeClient],
    ) -> BridgeClient:
        if player.pk not in clients:
            assert player.synthetic, f"{player} isn't synthetic; refusing to reset their password"
            password = secrets.token_urlsafe(32)
            player.user.set_password(password)
            player.user.save(update_fields=["password"])

            # verify=False: base_url is either plain http:// (dev, where this is moot) or
            # caddy/Caddyfile's internal-only `caddy:8443` listener, whose self-signed cert
            # nothing outside the compose network could validate anyway -- see BridgeClient's
            # own docstring for why that's fine here specifically.
            client = BridgeClient(base_url, verify=False)
            client.log_in(player.user.username, password)
            clients[player.pk] = client

        return clients[player.pk]
