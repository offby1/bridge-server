from __future__ import annotations

import json

import bridge.card
import bridge.contract
import pytest
from django_eventstream.models import Event  # type: ignore[import-untyped]

from .models import Hand, Player, Table
from .testutils import set_auction_to


class CapturedEventsFromChannel:
    def __init__(self, channel_name: str) -> None:
        self._channel_name = channel_name
        self.events: list[Event] = []
        self._message_ids_before = set(
            Event.objects.filter(channel=channel_name).values_list("id", flat=True),
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.events = list(
            Event.objects.filter(channel=self._channel_name).exclude(
                id__in=self._message_ids_before
            )
        )
        return False


def test_auction_settled_messages(usual_setup) -> None:
    t = Table.objects.first()
    assert t is not None
    h = t.current_hand

    with CapturedEventsFromChannel(h.pk) as cap:
        set_auction_to(
            bridge.contract.Bid(level=1, denomination=bridge.card.Suit.DIAMONDS),
            h,
        )

    assert sum(["new-call" in e.data for e in cap.events]) == 4
    assert sum(["contract" in e.data for e in cap.events]) == 1

    serial_numbers = []
    for e in cap.events:
        if e.data:
            # I have no idea why I need to decode this *twice*
            data = json.loads(json.loads(e.data))

            if (sn := data.get("serial_number")) is not None:
                serial_numbers.append(sn)

    assert serial_numbers[0:3] == [0, 1, 2]


def test_player_can_always_see_played_hands(played_to_completion) -> None:
    p1 = Player.objects.get(pk=1)
    hand_count_before = p1.hands_played.count()
    assert hand_count_before > 0
    p1.break_partnership()
    assert p1.hands_played.count() == hand_count_before


@pytest.mark.usefixtures("played_almost_to_completion")
def test_sends_final_score() -> None:
    h = Hand.objects.get(pk=1)

    assert h.player_who_may_play is not None
    libPlayer = h.player_who_may_play.libraryThing()
    libCard = bridge.card.Card.deserialize("♠A")

    with CapturedEventsFromChannel(h.pk) as cap:
        h.add_play_from_player(player=libPlayer, card=libCard)

    def sought(datum):
        return "final_score" in datum and "table" in datum

    assert any(sought(d.data) for d in cap.events)


@pytest.mark.usefixtures("played_to_completion")
def test_sends_new_hand_event_to_table_channel() -> None:
    t1 = Table.objects.first()
    assert t1 is not None

    with CapturedEventsFromChannel(t1.event_channel_name) as cap:
        t1.next_board()

    assert any("new-hand" in m.data for m in cap.events)
