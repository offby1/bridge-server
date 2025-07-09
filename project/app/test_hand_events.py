from __future__ import annotations

from collections.abc import Iterable
import json

import bridge.card
import bridge.contract
import pytest
from django_eventstream.models import Event  # type: ignore[import-untyped]

from .models import Hand, Player
from .testutils import set_auction_to


@pytest.fixture(autouse=True)
def capture_events_in_database(settings):
    del settings.EVENTSTREAM_REDIS
    settings.EVENTSTREAM_STORAGE_CLASS = "django_eventstream.storage.DjangoModelStorage"


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
        self.events = (
            Event.objects.order_by("created")
            .filter(channel__in=self._channel_names)
            .exclude(id__in=self._message_ids_before)
        )
        return False


def assert_sane_numbering(json_messages: Iterable[str]) -> None:
    __tracebackhide__ = True

    all_parsed_messages = [json.loads(json.loads(m)) for m in json_messages if m]
    relevant_parsed_messages = [
        m for m in all_parsed_messages if ("new-call" in m or "new-play" in m)
    ]

    actual = [m.get("hand_event") for m in relevant_parsed_messages]

    bogons = [m for m in relevant_parsed_messages if m.get("hand_event") is None]
    if bogons:
        pytest.fail(f'Hey man, some messages in {bogons} lack a "hand_event" key')

    expected = list(range(len(actual)))
    if actual != expected:
        for m in relevant_parsed_messages:
            print(m)
        pytest.fail(f"{actual=} != {expected=} :-(")


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

    assert sum(["new-call" in e.data for e in hand_json_cap.events]) == 16
    assert_sane_numbering(
        (e.data for e in hand_json_cap.events if e.channel == hand_JSON_channels[0])
    )
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
def test_sends_final_score_just_to_table() -> None:
    h = Hand.objects.get(pk=1)

    assert h.player_who_may_play is not None
    libCard = bridge.card.Card.deserialize("♠A")

    hand_HTML_channels = [p.event_HTML_hand_channel for p in h.players()]

    with CapturedEventsFromChannels(*hand_HTML_channels) as hand_html_cap:
        with CapturedEventsFromChannels(h.event_table_html_channel) as table_cap:
            h.add_play_from_model_player(player=h.player_who_may_play, card=libCard)

    def sought(datum):
        return "final_score" in datum

    assert any(sought(d.data) for d in table_cap.events)
    assert not any(sought(d.data) for d in hand_html_cap.events)


def test_includes_dummy_in_new_play_event_for_opening_lead(usual_setup) -> None:
    h: Hand = usual_setup

    one_hand_JSON_channel = next(h.players()).event_JSON_hand_channel

    def add_play(card_string: str) -> None:
        seat = h.next_seat_to_play
        assert seat is not None
        player = h.player_who_controls_seat(seat=seat, right_this_second=True)

        h.add_play_from_model_player(
            player=player,
            card=bridge.card.Card.deserialize(card_string),
        )

    with CapturedEventsFromChannels(one_hand_JSON_channel) as hand_json_cap:
        with CapturedEventsFromChannels(h.event_table_html_channel) as table_HTML_cap:
            set_auction_to(
                bridge.contract.Bid(level=1, denomination=bridge.card.Suit.DIAMONDS),
                h,
            )
            add_play("d2")
            add_play("h2")
            add_play("s2")

    assert_sane_numbering((e.data for e in hand_json_cap.events))

    dummys_seen = tricks_seen = 0
    for e in table_HTML_cap.events:
        if not e.data:
            continue
        try:
            for k, v in json.loads(json.loads(e.data)).items():
                print(f"{k}: {str(v)[0:100]}")
        except Exception as ex:
            print(f"{ex=}")

        if "dummy_html" in e.data:
            dummys_seen += 1
        if "trick_html" in e.data:
            tricks_seen += 1

    # Everyone gets to see the dummy after the opening lead, and everyone gets to see the *updated* dummy after it has
    # played a card.
    assert dummys_seen == 2

    assert tricks_seen == 3
