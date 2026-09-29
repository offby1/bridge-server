"""End-to-end tests for app/management/commands/ai_bot.py.

Covers both acting mechanisms the command uses, per its own module docstring:

- A synthetic-only hand, driven purely through the public API -- login, hand
  reads, calls, plays -- exactly like the real service does for those seats.
- A hand seated by real (non-synthetic) players who've delegated it via
  `allow_bot_to_play_for_me`, driven straight through the ORM, with no HTTP
  login at all.

No Anthropic credentials needed for either: with none configured (the default in
tests), every decision falls back to the dumb heuristics, which is enough to prove
the service's own plumbing -- discovery via get_next_hand(), applying decisions the
right way for each kind of seat -- actually works. See app/test_ai_bot.py for
Claude-decision unit tests, and app/test_reference_client.py for a client that
drives the API by hand (not via this command).
"""

from __future__ import annotations

import pytest
from pytest_django.live_server_helper import LiveServer

from app.management.commands.ai_bot import Command
from app.models import Hand
from app.reference_client import BridgeClient
from app.testutils import create_a_tournament


@pytest.mark.django_db
def test_ai_bot_plays_a_synthetic_hand_to_completion(live_server: LiveServer) -> None:
    tournament = create_a_tournament(stage="playing", num_pairs=2, boards_per_round_per_table=1)
    tournament.tempo_seconds = 0
    tournament.save()

    hand: Hand = tournament.hands().get()
    assert not hand.is_complete

    command = Command()
    clients: dict[int, BridgeClient] = {}

    for _ in range(120):  # a whole auction plus all 52 plays, with slack
        hand.refresh_from_db()
        if hand.is_complete:
            break
        assert command.process_one(live_server.url, clients, ai_client=None)
    else:
        pytest.fail("Hand didn't complete within the expected number of moves")

    # Every synthetic seat should have gotten its own login -- nobody shares a
    # session, and nobody outside the four seated players was touched.
    assert len(clients) <= 4


@pytest.mark.django_db
def test_ai_bot_plays_a_human_delegated_hand_to_completion(usual_setup: Hand) -> None:
    hand = usual_setup
    assert not hand.is_complete

    for direction in ("North", "East", "South", "West"):
        player = getattr(hand, direction)
        assert not player.synthetic
        player.allow_bot_to_play_for_me = True
        player.save()

    tournament = hand.board.tournament
    tournament.tempo_seconds = 0
    tournament.save()

    command = Command()
    # No seat here is synthetic, so this should never be touched -- there's nothing
    # to log in to.
    clients: dict[int, BridgeClient] = {}

    for _ in range(120):  # a whole auction plus all 52 plays, with slack
        hand.refresh_from_db()
        if hand.is_complete:
            break
        assert command.process_one("http://unused", clients, ai_client=None)
    else:
        pytest.fail("Hand didn't complete within the expected number of moves")

    assert clients == {}
