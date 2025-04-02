import logging

import pytest

import app.models
import bridge.contract
import bridge.table
from app.models.utils import assert_type

logger = logging.getLogger(__name__)


def set_auction_to(bid: bridge.contract.Bid, hand: app.models.Hand) -> app.models.Hand:
    assert_type(hand, app.models.Hand)

    def next_caller(current_caller: bridge.table.Player) -> bridge.table.Player:
        libTable = hand.auction.table
        return libTable.get_lho(current_caller)

    assert len(hand.auction.player_calls) == 0

    caller = hand.auction.allowed_caller()
    assert caller is not None

    hand.add_call_from_player(player=caller, call=bid)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 1
    caller = next_caller(caller)

    hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 2
    caller = next_caller(caller)

    hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 3
    caller = next_caller(caller)

    hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 4
    assert hand.auction.found_contract

    return hand


def play_out_hand(h: app.models.Hand) -> None:
    logger.info(f"Playing out {h=} (tournament #{h.tournament.display_number})")
    if h.is_complete:
        pytest.fail(f"Yo Vinnie: y u want to play out {h=} which is already complete?!")

    while (p := h.player_who_may_call) is not None:
        call = h.get_xscript().auction.legal_calls()[0]
        h.add_call_from_player(player=p.libraryThing(), call=call)

    while (p := h.player_who_may_play) is not None:
        play = h.get_xscript().slightly_less_dumb_play()
        h.add_play_from_player(player=p.libraryThing(), card=play.card)
        h.get_xscript().add_card(play.card)

    logger.info(f"After: {h.is_complete=}")
    if h.is_complete:
        return

    pytest.fail(f"Uh oh, we didn't make any calls or plays in {h}")


def play_out_round(tournament: app.models.Tournament) -> None:
    num_completed_rounds, _ = tournament.rounds_played()

    while True:
        hand = find_incomplete_hand(tournament)
        if hand is None:
            if (
                not tournament.is_complete
                and tournament.hands().count() == tournament.get_movement().total_hands
            ):
                pytest.fail(
                    f"since we found no incomplete hands (out of {tournament.hands().count()}), why is {tournament=} not complete?"
                )
        before = tournament.rounds_played()
        assert hand is not None
        play_out_hand(hand)
        tournament.refresh_from_db()
        after = tournament.rounds_played()

        if not after > before:
            pytest.fail(f"After playing a hand, {after=} should be greater than {before=}")

        if after[1] == 0:
            break


def find_incomplete_hand(tournament: app.models.Tournament) -> app.models.Hand | None:
    hands_created = tournament.hands().count()
    total = tournament.get_movement().total_hands
    logger.debug("%s has created %d hands out of %d", tournament, hands_created, total)

    completes = []
    incompletes = []
    for h in tournament.hands():
        if h.is_complete:
            completes.append(h)
        else:
            incompletes.append(h)

    logger.debug(
        "%s has %d complete hands, and %d incomplete hands",
        tournament,
        len(completes),
        len(incompletes),
    )
    for h in completes:
        logger.debug("%s is complete", h)
    for h in incompletes:
        logger.debug("%s is not complete", h)
    if not incompletes:
        return None
    return incompletes[0]
