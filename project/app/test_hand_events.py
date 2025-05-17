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


class CapturedEventsFromChannels:
    def __init__(self, *channel_names: str) -> None:
        self._channel_names = channel_names
        self.events: list[Event] = []
        self._message_ids_before = set(
            Event.objects.filter(channel__in=channel_names).values_list("id", flat=True),
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.events = list(
            Event.objects.filter(channel__in=self._channel_names).exclude(
                id__in=self._message_ids_before
            )
        )
        return False


def test_auction_settled_messages(usual_setup) -> None:
    h = usual_setup

    hand_HTML_channels = [p.event_HTML_hand_channel for p in h.players()]
    hand_JSON_channels = [p.event_JSON_hand_channel for p in h.players()]
    table_channels = [h.event_table_html_channel]

    with CapturedEventsFromChannels(*hand_HTML_channels) as hand_html_cap:
        with CapturedEventsFromChannels(*hand_JSON_channels) as hand_json_cap:
            with CapturedEventsFromChannels(*table_channels) as table_cap:
                set_auction_to(
                    bridge.contract.Bid(level=1, denomination=bridge.card.Suit.DIAMONDS),
                    h,
                )

    def summarize(thing):
        if isinstance(thing, str):
            return thing[0:10]
        elif isinstance(thing, dict):
            return {k: summarize(v) for k, v in thing.items()}
        else:
            return thing

    def p(wat):
        while True:
            try:
                wat = json.loads(wat)
            except Exception:
                return summarize(wat)

    assert sum(["new-call" in e.data for e in hand_json_cap.events]) == 16
    assert sum(["contract" in e.data for e in table_cap.events]) == 1

    # Between two and four bidding box HTMLs per call.  Two would be if we were efficient, and only re-sent them when
    # they went from active to inactive, or vice-versa; four would be if we were dumb and just always sent it, even if
    # it was inactive on the last call and is inactive on the current call.
    assert 2 * 4 <= sum(["bidding_box_html" in e.data for e in hand_html_cap.events]) <= 4 * 4


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

    with CapturedEventsFromChannels(h.event_table_html_channel) as cap:
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

    with CapturedEventsFromChannels(h.event_table_html_channel) as cap:
        h.add_play_from_player(
            # opening lead from East
            player=h.player_who_may_play.libraryThing(),
            card=bridge.card.Card.deserialize("d2"),
        )

    data = json.loads(json.loads(cap.events[0].data))
    dummy = data.get("dummy")
    # TODO -- we shouldn't insist on this order
    assert dummy == "♥2♥3♥4♥5♥6♥7♥8♥9♥T♥J♥Q♥K♥A"

    with CapturedEventsFromChannels(h.event_table_html_channel) as cap:
        h.add_play_from_player(
            # play from South
            player=h.player_who_may_play.libraryThing(),
            card=bridge.card.Card.deserialize("h2"),
        )

    data = json.loads(json.loads(cap.events[0].data))
    assert "dummy" not in data
