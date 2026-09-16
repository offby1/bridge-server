"""Play synthetic (bot-created) seats using Claude, via the public bridge API.

Unlike cheating_bot.py, this never touches the ORM to read game state or apply a
call or play -- it authenticates as each synthetic Player over HTTP (see
app/reference_client.py) and drives them through /call/ and /play/, the way any
other third-party client would. See docs/ai-bot-plan.md.

It only ever acts for Player rows with synthetic=True: dedicated bot placeholders
created by Player.create_synthetic_partner() to fill out a table, never a real
human's account -- cheating_bot.py keeps handling every other
allow_bot_to_play_for_me seat, unchanged. Since nobody else ever logs into a
synthetic account, this sets its own (random, per-run) password on one the first
time it needs to act for it, purely so it can log in -- game decisions and state
changes never go through the ORM.

Falls back to the same dumb heuristics cheating_bot.py uses -- see
app.ai_bot.decide_call()/decide_play() -- whenever Claude isn't available: no API
key configured, the AI_BOT_DISABLED kill switch is set (see
docs/ai-bot-cost-controls-plan.md), or the API call itself fails.
"""

from __future__ import annotations

import logging
import os
import secrets
import time

import anthropic
import app.ai_bot as ai_bot
import app.models
from app.management.commands.cheating_bot import get_next_hand, wait_for_tempo
from app.reference_client import BridgeClient, BridgeClientError
from django.core.management.base import BaseCommand

from bridge.seat import Seat
from bridge.xscript import HandTranscript

logger = logging.getLogger(__name__)


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
        """Find and act on one synthetic seat's turn, if there is one.

        Split out from `handle()`'s infinite loop so tests can call it directly, a
        bounded number of times, instead of looping forever.
        """
        hand = get_next_hand(logger=logger, synthetic=True)
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
            client = self._client_for(player, base_url, clients)
            xscript = HandTranscript.from_python(client.hand(hand.pk)["xscript"])

            call, reason = ai_bot.decide_call(ai_client, xscript, call_seat)
            # Waiting *here* -- after deciding, right before the write -- rather than
            # before any of the above means an API round-trip (often longer than
            # tempo_seconds on its own) counts *as* the wait instead of stacking on
            # top of a full tempo_seconds sleep. Only tops up whatever's left.
            wait_for_tempo(hand)
            client.call(call.serialize(), explanation=call.explanation)
            logger.info("hand %s: %s: %s (%s)", hand.pk, call_seat, call, reason)
            return

        play_seat = hand.next_seat_to_play
        if play_seat is None:
            logger.error("hand %s has a synthetic bot up but nobody may call or play", hand.pk)
            return

        player = hand.player_who_controls_seat(play_seat, right_this_second=True)
        logger.info("hand %s: %s (%s) may play", hand.pk, play_seat, player.name)
        client = self._client_for(player, base_url, clients)
        xscript = HandTranscript.from_python(client.hand(hand.pk)["xscript"])

        my_hand = xscript.dealt_cards_by_seat[play_seat]
        assert my_hand is not None, f"{client} should be able to see {play_seat}'s own cards"
        already_played = {p.card for p in xscript.plays() if p.seat == play_seat}
        legal = xscript.legal_cards(some_cards=[c for c in my_hand if c not in already_played])

        card, reason = ai_bot.decide_play(ai_client, xscript, play_seat, legal)
        wait_for_tempo(hand)
        client.play(str(card))
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

            client = BridgeClient(base_url)
            client.log_in(player.user.username, password)
            clients[player.pk] = client

        return clients[player.pk]
