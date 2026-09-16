"""Unit tests for app/ai_bot.py's decision-making, with a mocked Anthropic client.

No network calls, no API key needed, no Django database -- these test prompt
construction and response parsing against real `bridge` library objects, the same
way bridge/test_xscript.py in the library itself does.
"""

from __future__ import annotations

import random
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from bridge.auction import Auction
from bridge.card import Card, Rank, Suit
from bridge.contract import Bid, Pass
from bridge.main import sample_auction, sample_deal
from bridge.seat import Seat
from bridge.xscript import HandTranscript

from app import ai_bot


def _fake_response(
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    stop_reason: str = "tool_use",
    stop_details: Any = None,
) -> Any:
    block = SimpleNamespace(type="tool_use", name=tool_name, input=tool_input, id="toolu_1")
    return SimpleNamespace(stop_reason=stop_reason, content=[block], stop_details=stop_details)


@pytest.fixture
def fresh_xscript() -> HandTranscript:
    """A brand-new deal, nobody's called yet."""
    table, cards_by_seat = sample_deal(shuffle_deck=False)
    auction = Auction(table=table, dealer=Seat.NORTH)
    return HandTranscript(
        table=table,
        auction=auction,
        ns_vuln=False,
        ew_vuln=False,
        dealt_cards_by_seat=cards_by_seat,
    )


@pytest.fixture
def in_play_xscript() -> HandTranscript:
    """A deal with a completed (dumb-bot) auction, ready for the opening lead."""
    random.seed(42)  # an unshuffled deck reliably passes out; this one doesn't
    table, cards_by_seat = sample_deal(shuffle_deck=True)
    auction = sample_auction(table=table, cards_by_seat=cards_by_seat)
    return HandTranscript(
        table=table,
        auction=auction,
        ns_vuln=False,
        ew_vuln=False,
        dealt_cards_by_seat=cards_by_seat,
    )


def test_choose_call_returns_the_bid_the_model_picked(fresh_xscript: HandTranscript) -> None:
    seat = Seat.NORTH
    opening_bid = Bid(level=1, denomination=Suit.CLUBS)
    client = MagicMock()
    client.messages.create.return_value = _fake_response(
        tool_name="make_call",
        tool_input={
            "call": opening_bid.serialize(),
            "explanation": "Opening one club, my longest suit.",
        },
    )

    call = ai_bot.choose_call(client=client, xscript=fresh_xscript, seat=seat)

    assert call == opening_bid
    assert call.explanation == "Opening one club, my longest suit."

    kwargs = client.messages.create.call_args.kwargs
    tool = kwargs["tools"][0]
    offered = set(tool["input_schema"]["properties"]["call"]["enum"])
    legal = {c.serialize() for c in fresh_xscript.auction.legal_calls()}
    assert offered == legal
    assert kwargs["tool_choice"] == {"type": "tool", "name": "make_call"}
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_choose_call_raises_on_refusal(fresh_xscript: HandTranscript) -> None:
    client = MagicMock()
    client.messages.create.return_value = _fake_response(
        tool_name="make_call",
        tool_input={},
        stop_reason="refusal",
        stop_details=SimpleNamespace(category="other", explanation="nope"),
    )

    with pytest.raises(ai_bot.AIBotError):
        ai_bot.choose_call(client=client, xscript=fresh_xscript, seat=Seat.NORTH)


def test_choose_call_raises_if_model_skips_the_tool(fresh_xscript: HandTranscript) -> None:
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="I'd rather not.")],
        stop_details=None,
    )

    with pytest.raises(ai_bot.AIBotError):
        ai_bot.choose_call(client=client, xscript=fresh_xscript, seat=Seat.NORTH)


def test_choose_call_raises_if_model_picks_an_illegal_call(fresh_xscript: HandTranscript) -> None:
    client = MagicMock()
    client.messages.create.return_value = _fake_response(
        tool_name="make_call",
        tool_input={"call": "not a call", "explanation": "oops"},
    )

    with pytest.raises(ai_bot.AIBotError):
        ai_bot.choose_call(client=client, xscript=fresh_xscript, seat=Seat.NORTH)


def test_choose_call_skips_the_api_when_only_one_legal_call(
    fresh_xscript: HandTranscript,
) -> None:
    # Forcing exactly one legal call (e.g. after 7NT) is fiddly to set up for real, so
    # patch legal_calls() directly to exercise the shortcut.
    fresh_xscript.auction.legal_calls = lambda: [Pass]  # type: ignore[method-assign]

    client = MagicMock()
    call = ai_bot.choose_call(client=client, xscript=fresh_xscript, seat=Seat.NORTH)

    assert call is Pass
    client.messages.create.assert_not_called()


def test_choose_play_returns_the_card_the_model_picked(in_play_xscript: HandTranscript) -> None:
    xscript = in_play_xscript
    seat = xscript.next_seat_to_play()
    assert seat is not None
    hand = xscript.dealt_cards_by_seat[seat]
    assert hand
    legal_cards = xscript.legal_cards(some_cards=hand)
    chosen = legal_cards[0]

    client = MagicMock()
    client.messages.create.return_value = _fake_response(
        tool_name="play_card",
        tool_input={"card": chosen.serialize(), "explanation": "Leading low."},
    )

    card, explanation = ai_bot.choose_play(
        client=client, xscript=xscript, seat=seat, legal_cards=legal_cards
    )

    assert card == chosen
    assert explanation == "Leading low."
    kwargs = client.messages.create.call_args.kwargs
    tool = kwargs["tools"][0]
    assert set(tool["input_schema"]["properties"]["card"]["enum"]) == {
        c.serialize() for c in legal_cards
    }


def test_choose_play_raises_if_model_picks_a_card_not_offered(
    in_play_xscript: HandTranscript,
) -> None:
    xscript = in_play_xscript
    seat = xscript.next_seat_to_play()
    assert seat is not None
    hand = xscript.dealt_cards_by_seat[seat]
    assert hand
    legal_cards = xscript.legal_cards(some_cards=hand)

    not_offered = next(c for c in Card.deck() if c not in legal_cards)

    client = MagicMock()
    client.messages.create.return_value = _fake_response(
        tool_name="play_card",
        tool_input={"card": not_offered.serialize(), "explanation": "oops"},
    )

    with pytest.raises(ai_bot.AIBotError):
        ai_bot.choose_play(client=client, xscript=xscript, seat=seat, legal_cards=legal_cards)


def test_choose_play_skips_the_api_with_one_card_left(fresh_xscript: HandTranscript) -> None:
    # With only one legal card, there's nothing to decide -- the shortcut never
    # touches xscript, so a pre-play transcript is fine here.
    last_card = Card(suit=Suit.SPADES, rank=Rank.ACE)

    client = MagicMock()
    card, explanation = ai_bot.choose_play(
        client=client, xscript=fresh_xscript, seat=Seat.NORTH, legal_cards=[last_card]
    )

    assert card is last_card
    assert explanation
    client.messages.create.assert_not_called()


def test_decide_call_labels_an_ai_explanation_for_the_ui(fresh_xscript: HandTranscript) -> None:
    # decide_call()'s whole point is a human watching the game can tell whether Claude
    # or the fallback made a given call, via the *posted* explanation -- not just a
    # string this function happens to also return for our own log lines.
    opening_bid = Bid(level=1, denomination=Suit.CLUBS)
    client = MagicMock()
    client.messages.create.return_value = _fake_response(
        tool_name="make_call",
        tool_input={"call": opening_bid.serialize(), "explanation": "Longest suit."},
    )

    call, reason = ai_bot.decide_call(client, fresh_xscript, Seat.NORTH)

    assert call.explanation == "AI: Longest suit."
    assert reason == call.explanation


def test_decide_call_labels_the_dumb_bidder_explanation_for_the_ui(
    fresh_xscript: HandTranscript,
) -> None:
    call, reason = ai_bot.decide_call(None, fresh_xscript, Seat.NORTH)

    assert call.explanation.startswith("dumb bidder")
    assert reason == call.explanation
