from __future__ import annotations

import collections
import itertools

import bridge.card
import bridge.contract
import pytest

import app.models
import app.views
from . import testutils


@pytest.fixture(autouse=True)
def capture_events_in_database(settings):
    del settings.EVENTSTREAM_REDIS
    settings.EVENTSTREAM_STORAGE_CLASS = "django_eventstream.storage.DjangoModelStorage"


@pytest.fixture()
def sent_events_by_channel(monkeypatch):
    rv = collections.defaultdict(list)

    def send_event(*args, **kwargs) -> None:
        rv[kwargs["channel"]].append(kwargs)

    monkeypatch.setattr(app.models.hand, "send_event", send_event)

    return rv


def test_auction_settled_messages(usual_setup, sent_events_by_channel) -> None:
    h = usual_setup

    testutils.set_auction_to(
        bridge.contract.Bid(level=1, denomination=bridge.card.Suit.DIAMONDS),
        h,
    )

    player_JSON_events = list(
        itertools.chain.from_iterable(
            (v for k, v in sent_events_by_channel.items() if "player:json:" in k)
        )
    )
    player_HTML_events = list(
        itertools.chain.from_iterable(
            (v for k, v in sent_events_by_channel.items() if "player:html:" in k)
        )
    )
    table_HTML_events = list(
        itertools.chain.from_iterable(
            (v for k, v in sent_events_by_channel.items() if "table:html:" in k)
        )
    )

    # Four calls, each sent to all four players.
    calls_seen = 0
    for e in player_JSON_events:
        if "new-call" in e["data"]:
            calls_seen += 1
    assert calls_seen == 16

    assert sum(["contract" in e["data"] for e in table_HTML_events]) == 1

    # Between two and four bidding box HTMLs per call.  Two would be if we were efficient, and only re-sent them when
    # they went from active to inactive, or vice-versa; four would be if we were dumb and just always sent it, even if
    # it was inactive on the last call and is inactive on the current call.
    assert 2 * 4 <= sum(["bidding_box_html" in e["data"] for e in player_HTML_events]) <= 4 * 4


def test_player_can_always_see_played_hands(two_boards_one_is_complete) -> None:
    p1 = app.models.Player.objects.get(pk=1)
    hand_count_before = p1.hands_played.count()
    assert hand_count_before > 0
    p1.break_partnership()
    assert p1.hands_played.count() == hand_count_before


@pytest.mark.usefixtures("two_boards_one_of_which_is_played_almost_to_completion")
def test_sends_final_score(monkeypatch, sent_events_by_channel) -> None:
    from .models import Hand

    h1: Hand = Hand.objects.get(pk=1)
    player = h1.player_who_may_play
    assert player is not None
    libCard = bridge.card.Card.deserialize("♠A")

    h1.add_play_from_model_player(player=player, card=libCard)

    assert any("final_score" in e["data"] for e in sent_events_by_channel["table:html:1"])


def test_includes_dummy_in_new_play_event_for_opening_lead(
    usual_setup, sent_events_by_channel, monkeypatch
) -> None:
    h: app.models.Hand = usual_setup

    def add_play(card_string: str) -> None:
        seat = h.next_seat_to_play
        assert seat is not None
        player = h.player_who_controls_seat(seat=seat, right_this_second=True)

        h.add_play_from_model_player(
            player=player,
            card=bridge.card.Card.deserialize(card_string),
        )

    # So that our events contain, not HTML, but simple dicts.  That way we don't have to parse 'em.
    monkeypatch.setattr(app.views.hand, "render_to_string", lambda template_name, context: context)

    testutils.set_auction_to(
        bridge.contract.Bid(level=1, denomination=bridge.card.Suit.DIAMONDS),
        h,
    )

    add_play("d2")
    add_play("h2")
    add_play("s2")

    player_HTML_events = list(
        itertools.chain.from_iterable(
            (v for k, v in sent_events_by_channel.items() if "player:html:" in k)
        )
    )
    table_HTML_events = list(
        itertools.chain.from_iterable(
            (v for k, v in sent_events_by_channel.items() if "table:html:" in k)
        )
    )

    tricks_seen = 0

    for e in table_HTML_events:
        if "trick_html" in e["data"]:
            tricks_seen += 1

    assert tricks_seen == 3

    # Everyone gets to see the dummy.
    dummys_seen = 0

    for e in player_HTML_events:
        if (current_hand_html := e["data"].get("current_hand_html")) is not None:
            if current_hand_html.get("id") == "South":
                dummys_seen += 1

    """
    Trick 1: East.              Everyone gets a dummy message because this is the opening lead.
    Trick 2: South.             Everyone gets a dummy message because South *is* the dummy, and just played a card.
    Trick 3: West.              Nobody gets a dummy message, since nothing has changed in dummy-land.
    Trick 4: North.             Nobody gets a dummy message, since nothing has changed in dummy-land.

    """

    assert dummys_seen == 8


def test_dummys_hand_isnt_always_highlighted(
    usual_setup, monkeypatch, sent_events_by_channel
) -> None:
    h = usual_setup

    testutils.set_auction_to(
        bridge.contract.Bid(level=1, denomination=bridge.card.Suit.DIAMONDS),
        h,
    )

    assert h.dummy.seat.name == "South"

    # So that our events contain, not HTML, but simple dicts.  That way we don't have to parse 'em.
    monkeypatch.setattr(app.views.hand, "render_to_string", lambda template_name, context: context)

    for card in ("d2", "h2", "s2", "c2"):
        ns = h.next_seat_to_play
        h.add_play_from_model_player(
            player=h.player_who_controls_seat(ns, right_this_second=True),
            card=bridge.card.Card.deserialize(card),
        )

    active_seats_seen = set()
    for e in itertools.chain.from_iterable(
        sent_events_by_channel[p.event_HTML_hand_channel] for p in h.players()
    ):
        data = e.get("data", {})
        if (active_seat := data.get("current_hand_html", {}).get("active_seat")) is not None:
            active_seats_seen.add(active_seat)

    assert "South" in active_seats_seen
    assert len(active_seats_seen) > 1


def test_end_of_tournament(nearly_completed_tournament) -> None:
    def abandoned_hands():
        return nearly_completed_tournament.hands().filter(abandoned_because__isnull=False)

    assert not nearly_completed_tournament.is_complete
    assert abandoned_hands().count() == 0

    hand: app.models.Hand = nearly_completed_tournament.hands().filter(is_complete=False).first()
    assert hand is not None
    hand.add_play_from_model_player(player=hand.West, card=bridge.card.Card.deserialize("SA"))

    nearly_completed_tournament.refresh_from_db()

    assert nearly_completed_tournament.is_complete
    assert abandoned_hands().count() == 0
