from __future__ import annotations

import json

import bridge.card
import bridge.contract
import pytest
from django_eventstream.models import Event  # type: ignore[import-untyped]

from .models import Hand, Player
from .testutils import set_auction_to


class CapturedEvents:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self._message_ids_before = set(
            Event.objects.values_list("id", flat=True),
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.events = list(Event.objects.exclude(id__in=self._message_ids_before))
        return False


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
    h = usual_setup

    with CapturedEventsFromChannel(h.event_table_html_channel) as cap:
        set_auction_to(
            bridge.contract.Bid(level=1, denomination=bridge.card.Suit.DIAMONDS),
            h,
        )

    assert sum(["new-call" in e.data for e in cap.events]) == 4
    assert sum(["contract" in e.data for e in cap.events]) == 1


def test_player_can_always_see_played_hands(two_boards_one_is_complete) -> None:
    p1 = Player.objects.get(pk=1)
    hand_count_before = p1.hands_played.count()
    assert hand_count_before > 0
    p1.break_partnership()
    assert p1.hands_played.count() == hand_count_before


@pytest.mark.usefixtures("two_boards_one_of_which_is_played_almost_to_completion")
def test_sends_final_score() -> None:
    h = Hand.objects.get(pk=1)

    assert h.player_who_may_play is not None
    libPlayer = h.player_who_may_play.libraryThing()
    libCard = bridge.card.Card.deserialize("♠A")

    with CapturedEventsFromChannel(h.event_table_html_channel) as cap:
        h.add_play_from_player(player=libPlayer, card=libCard)

    def sought(datum):
        return "final_score" in datum and "table" in datum

    assert any(sought(d.data) for d in cap.events)


def test_includes_dummy_in_new_play_event_for_opening_lead(usual_setup) -> None:
    h = usual_setup
    set_auction_to(
        bridge.contract.Bid(level=1, denomination=bridge.card.Suit.DIAMONDS),
        h,
    )

    with CapturedEventsFromChannel(h.event_table_html_channel) as cap:
        h.add_play_from_player(
            # opening lead from East
            player=h.player_who_may_play.libraryThing(),
            card=bridge.card.Card.deserialize("d2"),
        )

    data = json.loads(json.loads(cap.events[0].data))
    dummy = data.get("dummy")
    # TODO -- we shouldn't insist on this order
    assert dummy == "♥2♥3♥4♥5♥6♥7♥8♥9♥T♥J♥Q♥K♥A"

    with CapturedEventsFromChannel(h.event_table_html_channel) as cap:
        h.add_play_from_player(
            # play from South
            player=h.player_who_may_play.libraryThing(),
            card=bridge.card.Card.deserialize("h2"),
        )

    data = json.loads(json.loads(cap.events[0].data))
    assert "dummy" not in data
