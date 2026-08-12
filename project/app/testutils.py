import datetime
import logging
from typing import Literal

import pytest
from django.utils import timezone

import app.broadcast
import app.models
import bridge.contract
import bridge.table
from app.models.tournament import _do_signup_expired_stuff
from app.models.utils import assert_type

logger = logging.getLogger(__name__)


def create_a_tournament(
    *,
    stage: Literal["open", "playing", "complete"] = "complete",
    num_pairs: int = 4,
    boards_per_round_per_table: int = 2,
) -> app.models.Tournament:
    """Create a tournament populated with `num_pairs` pairs of synthetic players.

    `stage` controls how far the tournament is advanced:

    - "open": open for signups; players are signed up but no hands exist yet.
    - "playing": signups are expired and round-0 hands are created, but none
      have been played.
    - "complete": every round is played out, so the returned tournament
      `.is_complete`.

    No `freeze_time` is needed: we sign players up while the tournament is open,
    then backdate `signup_deadline` so the movement can be computed.  The
    play-completion deadline (computed at signup expiry, ~tens of minutes out)
    stays comfortably ahead of the instantaneous playout.
    """
    t = app.models.Tournament.objects.create(
        boards_per_round_per_table=boards_per_round_per_table,
    )

    # Sign up only the pairs we just made; signing up `Player.objects.all()`
    # would sweep in already-seated players from other tournaments and fail the
    # not-seated check in sign_up_player_and_partner().
    created_pairs = []
    for _ in range(num_pairs):
        p1 = app.models.Player.objects.create_synthetic()
        p2 = app.models.Player.objects.create_synthetic()
        p1.partner_with(p2)
        created_pairs.append(p1)

    for p in created_pairs:
        t.sign_up_player_and_partner(p)

    # No hands exist until the signup deadline expires.
    assert not t.hands().exists(), f"{t} has hands before its signup deadline expired"

    if stage == "open":
        return t

    # The signup deadline must be in the past before a movement can be
    # computed, but it had to be in the future (above) for signups to be
    # accepted.  Backdate it now that everyone's signed up.
    t.signup_deadline = timezone.now() - datetime.timedelta(seconds=10)
    t.save()

    _do_signup_expired_stuff(t)

    # Expiry creates exactly one hand per table for the first round.
    num_tables = len(t.get_movement().table_settings_by_zb_table_number)
    assert t.hands().count() == num_tables, (
        f"{t}: expected one hand per table ({num_tables}), got {t.hands().count()}"
    )

    if stage == "complete":
        t.refresh_from_db()
        while not t.is_complete:
            play_out_round(t)
            t.refresh_from_db()

    t.refresh_from_db()
    return t


def set_auction_to(bid: bridge.contract.Bid, hand: app.models.Hand) -> app.models.Hand:
    assert_type(hand, app.models.Hand)

    def next_caller(current_caller: bridge.table.Player) -> bridge.table.Player:
        libTable = hand.auction.table
        return libTable.get_lho(current_caller)

    assert len(hand.auction.player_calls) == 0

    caller = hand.auction.allowed_caller()
    assert caller is not None

    hand.add_call(call=bid)
    # Emulate the notifier: a committed call fires the broadcast the notifier
    # would fire in production (see docs/README.listen-notify.md).
    app.broadcast.broadcast_after_call(hand=hand)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 1
    caller = next_caller(caller)

    hand.add_call(call=bridge.contract.Pass)
    app.broadcast.broadcast_after_call(hand=hand)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 2
    caller = next_caller(caller)

    hand.add_call(call=bridge.contract.Pass)
    app.broadcast.broadcast_after_call(hand=hand)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 3
    caller = next_caller(caller)

    hand.add_call(call=bridge.contract.Pass)
    app.broadcast.broadcast_after_call(hand=hand)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 4
    assert hand.auction.found_contract

    return hand


def play_out_hand(h: app.models.Hand) -> None:
    if h.is_complete:
        pytest.fail(f"Yo Vinnie: y u want to play out {h=} which is already complete?!")

    while h.player_who_may_call is not None:
        call = h.get_xscript().auction.legal_calls()[0]
        h.add_call(call=call)
        app.broadcast.broadcast_after_call(hand=h)

    while (ns := h.next_seat_to_play) is not None:
        play = h.get_xscript().slightly_less_dumb_play()
        h.add_play_from_model_player(
            player=h.player_who_controls_seat(ns, right_this_second=True), card=play.card
        )

    if h.is_complete:
        logger.info("%s played %s to completion", [p.name for p in h.players()], h)
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
    for h in tournament.hands():
        if not h.is_complete:
            return h

    return None
