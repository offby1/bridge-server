from __future__ import annotations

import collections
from typing import Any

import bridge.card
import bridge.contract
import pytest
from django_eventstream.models import Event  # type: ignore[import-untyped]

from .models import Player, Table, hand
from .testutils import set_auction_to


def test_auction_settled_messages(usual_setup, monkeypatch) -> None:
    t = Table.objects.first()
    assert t is not None
    h = t.current_hand

    sent_events: list[dict[str, Any]] = []

    def send_timestamped_event(*, channel: str, data: dict[str, Any]) -> None:
        sent_events.append({"channel": channel, "data": data})

    monkeypatch.setattr(hand, "send_timestamped_event", send_timestamped_event)

    set_auction_to(bridge.contract.Bid(level=1, denomination=bridge.card.Suit.DIAMONDS), h)

    serial_numbers = []
    hand_event_counts_by_top_level_keys: collections.Counter[str] = collections.Counter()
    for e in sent_events:
        # let's only look at events for the hand
        if e["channel"] == "1":
            serial_numbers.append(e["data"]["serial_number"])
            for k in e["data"]:
                hand_event_counts_by_top_level_keys[k] += 1

    assert hand_event_counts_by_top_level_keys["new-call"] == 4
    assert hand_event_counts_by_top_level_keys["contract"] == 1

    assert serial_numbers[0:3] == [0, 1, 2]


def test_player_can_always_see_played_hands(played_to_completion) -> None:
    p1 = Player.objects.get(pk=1)
    hand_count_before = p1.hands_played.count()
    assert hand_count_before > 0
    p1.break_partnership()
    assert p1.hands_played.count() == hand_count_before


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


@pytest.mark.usefixtures("played_to_completion")
def test_sends_new_hand_event_to_table_channel() -> None:
    t1 = Table.objects.first()
    assert t1 is not None
    filter_dict = {"channel": t1.event_channel_name}

    message_ids_before = set(
        Event.objects.filter(**filter_dict).values_list("id", flat=True),
    )

    t1.next_board()

    messages_after = Event.objects.filter(**filter_dict).exclude(id__in=message_ids_before)

    assert any("new-hand" in m.data for m in messages_after)
