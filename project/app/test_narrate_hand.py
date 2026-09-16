"""Play one hand start to finish purely through the public bot API, narrating each
call and play to stdout as it happens.

This exists to *watch* the bot API actually work end-to-end, the way
`docs/ai-bot-plan.md`'s eventual AI bot will use it -- not just assert individual
behaviors the way the rest of `app/test_reference_client.py` does.

If an Anthropic API key is available (`ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` --
see app/ai_bot.py), calls and plays come from Claude, via `app.ai_bot.choose_call()`/
`choose_play()`. Without one -- the default, so this stays free and network-independent
by default -- it falls back to the same dumb heuristics `cheating_bot.py` uses:
`make_standard_american_call()` for bidding (only needs your own hand plus the public
auction, which a real API client legitimately has), and the lowest legal card for play
(not `slightly_less_dumb_play()`, which double-dummy-solves all four hands -- something
a real API client, seeing only its own cards plus dummy's once exposed, never can). The
AI path falls back to the same dumb heuristics too, on any API error.

Run with `just narrate-hand` (add `-k pattern` to skip straight to this test; see the
justfile). Pass `-s` (already on by default there) to see the narration as it prints.
"""

from __future__ import annotations

import logging

import anthropic
import pytest
from pytest_django.live_server_helper import LiveServer

from app import ai_bot
from app.models import Hand
from app.reference_client import BridgeClient
from bridge.card import Card
from bridge.contract import Contract
from bridge.seat import Seat
from bridge.xscript import HandTranscript

PASSWORD = "sekrit"


def _log_in_every_seat(hand: Hand, live_server: LiveServer) -> dict[Seat, BridgeClient]:
    """Give each of the four seated players a known password, log in as each over
    HTTP, and figure out who's sitting where -- all so the loop below can act purely
    through the API from here on.
    """
    clients_by_username: dict[str, BridgeClient] = {}
    for direction in ("North", "East", "South", "West"):
        player = getattr(hand, direction)
        player.user.set_password(PASSWORD)
        player.user.save()

        client = BridgeClient(live_server.url)
        client.log_in(player.user.username, PASSWORD)
        clients_by_username[player.user.username] = client

    any_client = next(iter(clients_by_username.values()))
    table = any_client.hand(hand.pk)["xscript"]["table"]
    return {Seat.from_python(entry["seat"]): clients_by_username[entry["name"]] for entry in table}


def _my_remaining_cards(xscript: HandTranscript, seat: Seat) -> list[Card]:
    # Callers only ever ask this for a seat whose cards *are* visible to whichever
    # client fetched xscript (their own, or dummy's once they're declarer) -- never a
    # seat redacted (None) from that viewpoint.
    dealt = xscript.dealt_cards_by_seat[seat]
    assert dealt is not None
    already_played = {p.card for p in xscript.plays() if p.seat == seat}
    return [c for c in dealt if c not in already_played]


@pytest.mark.django_db
def test_playing_a_hand_via_the_api(usual_setup: Hand, live_server: LiveServer) -> None:
    hand = usual_setup
    client_by_seat = _log_in_every_seat(hand, live_server)
    north_username = hand.North.user.username
    hand_pk = hand.pk
    ai_client = ai_bot.client_if_enabled()
    print(
        "\nDecisions come from "
        + ("Claude (an API key is set)." if ai_client is not None else "the dumb heuristics (no API key set).")
    )

    # The live server's own request/access logging would otherwise drown out our
    # narration -- this is a demo people are meant to actually read.
    logging.disable(logging.INFO)
    try:
        # A four-pass auction is a legitimate, if boring, outcome, and this fixture's
        # dealt cards make it a likely one -- so if a board passes out, move on to the
        # next one (same table, same players) rather than call the demo done. The
        # fixture's own tournament deals boards_per_round_per_table of them (3, here).
        for board_number in range(1, 4):
            print(f"\n=== Board {board_number} (hand {hand_pk}) ===")
            if _play_the_hand(hand_pk, client_by_seat, ai_client):
                return
            # Passed out: log back in as anyone at the table to find the next hand --
            # the server moves everyone on to a fresh board automatically.
            body = client_by_seat[Seat.NORTH].log_in(north_username, PASSWORD)
            hand_pk = body["hand_pk"]
        pytest.skip("Every board in this fixture passed out; nothing to demonstrate")
    finally:
        logging.disable(logging.NOTSET)


def _play_the_hand(
    hand_pk: int,
    client_by_seat: dict[Seat, BridgeClient],
    ai_client: anthropic.Anthropic | None,
) -> bool:
    """Play hand_pk to completion via the API, narrating as it goes.

    Returns whether the auction actually reached a contract (as opposed to being
    passed out).
    """
    contract_announced = False
    xscript: HandTranscript
    seat: Seat | None

    for _ in range(120):  # a whole auction plus all 52 plays, with slack
        # Any seat's view agrees on whose turn it is and whether the hand is over --
        # only *card contents* are redacted per-viewer, not the public play-by-play.
        xscript = HandTranscript.from_python(
            next(iter(client_by_seat.values())).hand(hand_pk)["xscript"]
        )
        if xscript.is_complete():
            break

        if not isinstance(xscript.auction.status, Contract):
            caller = xscript.auction.allowed_caller()
            assert caller is not None
            seat = caller.seat
            client = client_by_seat[seat]
            my_xscript = HandTranscript.from_python(client.hand(hand_pk)["xscript"])

            call, reason = ai_bot.decide_call(ai_client, my_xscript, seat)
            print(f"{seat}: {call} ({reason})")
            client.call(call.serialize())
        else:
            contract = xscript.auction.status
            if not contract_announced:
                double_description = ""
                if contract.multiplier == 2:
                    double_description = ", doubled"
                elif contract.multiplier == 4:
                    double_description = ", redoubled"
                print(
                    f"\nOK, the contract is {contract.bid}{double_description}, "
                    f"played by {contract.declarer.name} (sitting {contract.declarer.seat}).\n"
                )
                contract_announced = True

            seat = xscript.next_seat_to_play()
            assert seat is not None

            # Declarer plays dummy's cards; nobody is ever logged in *as* dummy to do it.
            acting_seat = seat
            if seat == xscript.auction.dummy.seat:
                assert xscript.auction.declarer is not None
                acting_seat = xscript.auction.declarer.seat

            client = client_by_seat[acting_seat]
            my_xscript = HandTranscript.from_python(client.hand(hand_pk)["xscript"])
            legal = my_xscript.legal_cards(some_cards=_my_remaining_cards(my_xscript, seat))

            card, reason = ai_bot.decide_play(ai_client, my_xscript, seat, legal)
            print(f"{seat}: plays {card} ({reason})")
            client.play(str(card))
    else:
        pytest.fail("Hand didn't complete within the expected number of moves")

    print(f"\nHand complete. Score: {xscript.final_score()}\n")
    assert xscript.is_complete()
    return contract_announced
