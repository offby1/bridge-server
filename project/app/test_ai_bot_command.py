"""End-to-end test for app/management/commands/ai_bot.py.

Drives a hand where every seat is a synthetic player, purely through the public
API -- login, hand reads, calls, plays -- exactly like the real service does. No
Anthropic credentials needed: with none configured (the default in tests), every
decision falls back to the dumb heuristics, which is enough to prove the service's
own plumbing -- discovery via get_next_hand(synthetic=True), per-player login, and
applying calls/plays over HTTP -- actually works. See app/test_ai_bot.py for
Claude-decision unit tests, and app/test_narrate_hand.py for the human-seat
equivalent of this test.
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
