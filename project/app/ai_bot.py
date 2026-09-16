"""Claude-backed decisions for bridge calls and plays.

This is the decision-making core sketched in docs/ai-bot-plan.md: given a hand
transcript and a seat, ask Claude to choose a call or a card, constrained to
exactly the legal options via a forced tool call. It knows nothing about Django,
the bot API, or HTTP -- see app/reference_client.py and app/test_narrate_hand.py
for how a real driver wires this up to an actual hand.

Bidding uses `xscript.auction.legal_calls()`, which only needs the caller's own
hand plus the public auction -- information a real API client legitimately has.
Card play is likewise restricted to the acting seat's own legal cards. Neither
function ever sees or needs the full deal, unlike
`bridge.xscript.HandTranscript.slightly_less_dumb_play()`, which double-dummy-solves
all four hands and so only works server-side.

Callers should catch `AIBotError` (and anthropic's own exceptions) and fall back to
`bridge.auction.Auction.make_standard_american_call()` / any legal card -- see
docs/ai-bot-plan.md's "Resilience" section and docs/ai-bot-cost-controls-plan.md.
"""

from __future__ import annotations

import collections
from typing import Any

import anthropic
from anthropic.types import TextBlockParam, ToolParam
from bridge.card import Card, Suit
from bridge.contract import Bid, Call, Contract
from bridge.seat import Seat
from bridge.xscript import HandTranscript

DEFAULT_MODEL = "claude-sonnet-5"

RULES_PRIMER = """\
You are one seat at a table playing contract bridge, bidding and playing under \
Standard American conventions. You already know the rules and the conventions;
nothing here overrides your own judgment.

You'll be given your hand, the auction or the current trick so far, and (once
play has begun) dummy's hand once it's exposed. Choose your call or play using
the tool provided -- its options are already restricted to what's legal right
now, so pick whichever of them is the best bridge decision. Always fill in the
one-sentence explanation; your partner (human or otherwise) will see it.
"""

SUITS_HIGH_TO_LOW = list(reversed(list(Suit)))


class AIBotError(Exception):
    """The model's response couldn't be turned into a legal call or play."""


def default_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def choose_call(
    *,
    client: anthropic.Anthropic,
    xscript: HandTranscript,
    seat: Seat,
    model: str = DEFAULT_MODEL,
) -> Call:
    legal = list(xscript.auction.legal_calls())
    if len(legal) == 1:
        return legal[0]

    tool = _call_tool(legal)
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        output_config={"effort": "low"},
        system=_system_prompt(),
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": _describe_auction(xscript, seat)}],
    )
    tool_input = _tool_input(response, tool["name"])

    serialized = tool_input.get("call")
    try:
        call = Bid.deserialize(serialized) if isinstance(serialized, str) else None
    except Exception as e:
        raise AIBotError(f"model's call {serialized!r} doesn't parse: {e}") from e
    if call is None or call not in legal:
        msg = f"model chose {serialized!r}, which isn't one of the legal calls {legal!r}"
        raise AIBotError(msg)

    return call.with_explanation(str(tool_input.get("explanation", "")))


def choose_play(
    *,
    client: anthropic.Anthropic,
    xscript: HandTranscript,
    seat: Seat,
    legal_cards: list[Card],
    model: str = DEFAULT_MODEL,
) -> tuple[Card, str]:
    """Returns (card, explanation). Unlike Call, Card has no explanation slot of its
    own -- the wire format for a play is just the card -- so this hands it back
    separately for whoever wants to narrate or log it.
    """
    if len(legal_cards) == 1:
        return legal_cards[0], "it's the only card left"

    tool = _play_tool(legal_cards)
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        output_config={"effort": "low"},
        system=_system_prompt(),
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": _describe_play(xscript, seat, legal_cards)}],
    )
    tool_input = _tool_input(response, tool["name"])

    serialized = tool_input.get("card")
    try:
        card = Card.deserialize(serialized) if isinstance(serialized, str) else None
    except Exception as e:
        raise AIBotError(f"model's card {serialized!r} doesn't parse: {e}") from e
    if card is None or card not in legal_cards:
        msg = f"model chose {serialized!r}, which isn't one of the legal cards {legal_cards!r}"
        raise AIBotError(msg)

    return card, str(tool_input.get("explanation", ""))

    return card


def _system_prompt() -> list[TextBlockParam]:
    return [{"type": "text", "text": RULES_PRIMER, "cache_control": {"type": "ephemeral"}}]


def _call_tool(legal: list[Call]) -> ToolParam:
    return {
        "name": "make_call",
        "description": "Make your call: a bid, or Pass, Double, or Redouble.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "call": {"type": "string", "enum": [c.serialize() for c in legal]},
                "explanation": {
                    "type": "string",
                    "description": "One short sentence on why -- shown to your partner.",
                },
            },
            "required": ["call", "explanation"],
            "additionalProperties": False,
        },
    }


def _play_tool(legal_cards: list[Card]) -> ToolParam:
    return {
        "name": "play_card",
        "description": "Play one card from your hand.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "card": {"type": "string", "enum": [c.serialize() for c in legal_cards]},
                "explanation": {"type": "string", "description": "One short sentence on why."},
            },
            "required": ["card", "explanation"],
            "additionalProperties": False,
        },
    }


def _tool_input(response: Any, tool_name: str) -> dict[str, Any]:
    if response.stop_reason == "refusal":
        raise AIBotError(f"model refused: {response.stop_details}")
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input  # already a parsed dict; schema-validated by `strict`
    msg = f"model didn't call {tool_name!r} (stop_reason={response.stop_reason})"
    raise AIBotError(msg)


def _format_hand(cards: list[Card]) -> str:
    by_suit: dict[Suit, list[Card]] = collections.defaultdict(list)
    for c in cards:
        by_suit[c.suit].append(c)
    lines = []
    for suit in SUITS_HIGH_TO_LOW:
        ranked = sorted(by_suit[suit], key=lambda c: c.rank, reverse=True)
        spots = " ".join(str(c.rank) for c in ranked) if ranked else "--"
        lines.append(f"{suit}: {spots}")
    return "\n".join(lines)


def _describe_auction(xscript: HandTranscript, seat: Seat) -> str:
    auction = xscript.auction
    calls_so_far = (
        ", ".join(f"{pc.player.seat}: {pc.call.serialize()}" for pc in auction.player_calls)
        or "(nobody has called yet)"
    )
    hand = xscript.dealt_cards_by_seat[seat]
    assert hand is not None, f"{seat} is the caller, so we must know their own hand"
    return (
        f"You are {seat}. Dealer: {auction.dealer}. "
        f"Vulnerable: {_vuln_description(xscript)}.\n\n"
        f"Your hand:\n{_format_hand(hand)}\n\n"
        f"Auction so far: {calls_so_far}\n\n"
        "It's your turn to call."
    )


def _describe_play(xscript: HandTranscript, seat: Seat, legal_cards: list[Card]) -> str:
    contract = xscript.auction.status
    assert isinstance(contract, Contract)

    already_played = {p.card for p in xscript.plays() if p.seat == seat}
    my_hand = xscript.dealt_cards_by_seat[seat]
    assert my_hand is not None, f"{seat} is on play, so we must know their own hand"
    my_remaining = [c for c in my_hand if c not in already_played]

    lines = [
        f"You are {seat}. Contract: {contract.bid} played by {contract.declarer.name} "
        f"(sitting {contract.declarer.seat}).",
        "",
        f"Your remaining cards:\n{_format_hand(my_remaining)}",
    ]

    dummy_seat = xscript.auction.dummy.seat
    dummy_hand = xscript.dealt_cards_by_seat[dummy_seat]
    if dummy_hand is not None:
        dummy_already_played = {p.card for p in xscript.plays() if p.seat == dummy_seat}
        dummy_remaining = [c for c in dummy_hand if c not in dummy_already_played]
        lines += ["", f"Dummy ({dummy_seat})'s remaining cards:\n{_format_hand(dummy_remaining)}"]

    current_trick = xscript.tricks[-1] if xscript.tricks else None
    if current_trick is not None and not current_trick.is_complete() and len(current_trick):
        played_so_far = ", ".join(f"{p.seat}: {p.card}" for p in current_trick)
        lines += ["", f"Cards played in the current trick so far: {played_so_far}"]
    else:
        lines += ["", "You are leading this trick."]

    lines += ["", "It's your turn to play a card."]
    return "\n".join(lines)


def _vuln_description(xscript: HandTranscript) -> str:
    if xscript.ns_vuln and xscript.ew_vuln:
        return "both sides"
    if xscript.ns_vuln:
        return "North/South"
    if xscript.ew_vuln:
        return "East/West"
    return "neither side"
