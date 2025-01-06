from __future__ import annotations

import collections
from typing import Any

import bridge.card
import bridge.contract
import pytest

from .models import Player, Table
from .testutils import set_auction_to


def test_auction_settled_messages(usual_setup, monkeypatch) -> None:
    t = Table.objects.first()
    assert t is not None
    h = t.current_hand

    sent_events = []

    def send_event_to_players_and_hand(*, data: dict[str, Any]) -> None:
        sent_events.append(data)

    monkeypatch.setattr(h, "send_event_to_players_and_hand", send_event_to_players_and_hand)

    set_auction_to(bridge.contract.Bid(level=1, denomination=bridge.card.Suit.DIAMONDS), h)

    event_counts_by_top_level_keys: collections.Counter[str] = collections.Counter()
    for e in sent_events:
        for k in e:
            event_counts_by_top_level_keys[k] += 1

    assert event_counts_by_top_level_keys["new-call"] == 4
    assert event_counts_by_top_level_keys["contract"] == 1


def test_player_can_always_see_played_hands(played_to_completion) -> None:
    p1 = Player.objects.get(pk=1)
    hand_count_before = p1.hands_played.count()
    assert hand_count_before > 0
    p1.break_partnership()
    assert p1.hands_played.count() == hand_count_before


def test_new_hand_messages(played_to_completion, monkeypatch) -> None:
    t = Table.objects.first()
    assert t is not None

    sent_events_by_channel: collections.defaultdict[str, list[dict[str, Any]]] = (
        collections.defaultdict(list)
    )

    def send_timestamped_event(channel: str, data: dict[str, Any]) -> None:
        sent_events_by_channel[channel].append(data)

    from .models import hand

    monkeypatch.setattr(hand, "send_timestamped_event", send_timestamped_event)

    t.next_board()

    def num_visible_cards(unpacked_events=list[dict[str, Any]]) -> int:
        rv = 0
        for e in unpacked_events:
            match e:
                case {"new-hand": {"board": board_guts}}:
                    for dir_ in ("north", "east", "south", "west"):
                        key = f"{dir_}_cards"
                        if isinstance(board_guts, dict):
                            rv += len(board_guts.get(key, "")) // 2
        return rv

    for channel, events in sent_events_by_channel.items():
        assert num_visible_cards(events) == 0, f"{channel=} {num_visible_cards(events)} should be 0"


@pytest.mark.usefixtures("played_almost_to_completion")
def test_sends_final_score(monkeypatch) -> None:
    sent_events = []

    def send_timestamped_event(channel: str, data: dict[str, Any]) -> None:
        sent_events.append(data)

    from .models import Hand, hand

    monkeypatch.setattr(hand, "send_timestamped_event", send_timestamped_event)
    h1 = Hand.objects.get(pk=1)
    assert h1.player_who_may_play is not None
    libPlayer = h1.player_who_may_play.libraryThing()
    libCard = bridge.card.Card.deserialize("♠A")

    h1.add_play_from_player(player=libPlayer, card=libCard)

    def sought(datum):
        return "final_score" in datum and "table" in datum

    assert any(sought(d) for d in sent_events)
