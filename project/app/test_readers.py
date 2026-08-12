"""Tests for the readers in app/readers.py.

These call the readers straight, with no request and no test client: that is the
point of having moved them off the models and out of the views. See
docs/README.rapid-readers.md.

The readers that already had good coverage through the view tests are not
re-tested here. What is here covers the readers those tests never reached, and
the branches they never took.
"""

import pytest
from allauth.socialaccount.models import SocialAccount  # type: ignore[import-untyped]

import app.readers
import bridge.card
import bridge.contract
from app.models import Hand, Player
from app.testutils import create_a_tournament, play_out_hand, set_auction_to


def _play_it_out(hand: Hand) -> Hand:
    """Settle the auction on a real contract, then play all thirteen tricks.

    `play_out_hand` on its own picks the first legal call, which is Pass, so it
    passes the auction out and leaves a hand that is complete but has no tricks.
    Anything that wants tricks has to settle a contract first.
    """
    hand = set_auction_to(bridge.contract.Bid(level=1, denomination=bridge.card.Suit.SPADES), hand)
    play_out_hand(hand)
    return hand


def _a_player_at(hand: Hand, *, other_than: Player) -> Player:
    """Some player seated at `hand` who is not `other_than`."""
    for player in hand.players_by_direction_letter.values():
        if player.pk != other_than.pk:
            return player

    pytest.fail(f"{hand} seats nobody but {other_than}")


# get_hint_for_player


def test_hint_says_so_when_the_player_is_not_seated(nobody_seated: None) -> None:
    player = Player.objects.first()
    assert player is not None
    assert player.current_hand is None

    assert app.readers.get_hint_for_player(player) == f"{player} has no current hand"


def test_hint_suggests_a_call_to_whoever_is_on_turn_to_call(usual_setup: Hand) -> None:
    hand = usual_setup
    caller = hand.player_who_may_call
    assert caller is not None

    assert app.readers.get_hint_for_player(caller).startswith("If I were you, I'd call")


def test_hint_declines_for_someone_whose_turn_it_is_not(usual_setup: Hand) -> None:
    hand = usual_setup
    caller = hand.player_who_may_call
    assert caller is not None
    bystander = _a_player_at(hand, other_than=caller)

    hint = app.readers.get_hint_for_player(bystander)

    assert hint == f"It's not {bystander}'s turn to call or play"


def test_hint_suggests_a_card_once_the_auction_has_settled(usual_setup: Hand) -> None:
    hand = set_auction_to(
        bridge.contract.Bid(level=1, denomination=bridge.card.Suit.SPADES), usual_setup
    )

    seat_on_lead = hand.next_seat_to_play
    assert seat_on_lead is not None
    player_on_lead = hand.player_who_controls_seat(seat_on_lead, right_this_second=True)

    assert "I'd play" in app.readers.get_hint_for_player(player_on_lead)


def test_hint_during_play_tells_an_opponent_nothing(usual_setup: Hand) -> None:
    """Asking for a hint must not reveal the card the player on turn should play."""
    hand = set_auction_to(
        bridge.contract.Bid(level=1, denomination=bridge.card.Suit.SPADES), usual_setup
    )

    seat_on_lead = hand.next_seat_to_play
    assert seat_on_lead is not None
    player_on_lead = hand.player_who_controls_seat(seat_on_lead, right_this_second=True)
    bystander = _a_player_at(hand, other_than=player_on_lead)

    hint = app.readers.get_hint_for_player(bystander)

    assert hint == f"It's not {bystander}'s turn to call or play"


def test_hint_for_dummys_turn_goes_to_declarer_and_not_to_dummy(usual_setup: Hand) -> None:
    """Declarer plays dummy's cards, so declarer is the one entitled to the hint."""
    hand = set_auction_to(
        bridge.contract.Bid(level=1, denomination=bridge.card.Suit.SPADES), usual_setup
    )

    # The opening lead comes from declarer's left, and dummy plays next.
    seat_on_lead = hand.next_seat_to_play
    assert seat_on_lead is not None
    hand.add_play_from_model_player(
        player=hand.player_who_controls_seat(seat_on_lead, right_this_second=True),
        card=hand.get_xscript().slightly_less_dumb_play().card,
    )

    assert hand.dummy is not None
    assert hand.next_seat_to_play == hand.dummy.seat

    declarer = hand.model_declarer
    dummy = hand.model_dummy
    assert declarer is not None
    assert dummy is not None

    assert "I'd play" in app.readers.get_hint_for_player(declarer)
    assert app.readers.get_hint_for_player(dummy) == f"It's not {dummy}'s turn to call or play"


# get_xscript_updates


def test_xscript_updates_reports_the_calls_the_caller_has_not_seen(usual_setup: Hand) -> None:
    hand = set_auction_to(
        bridge.contract.Bid(level=1, denomination=bridge.card.Suit.SPADES), usual_setup
    )

    from_the_top = app.readers.get_xscript_updates(hand=hand, num_calls=0, num_plays=0)

    assert len(from_the_top["calls"]) == 4
    assert from_the_top["plays"] == []


def test_xscript_updates_reports_nothing_when_the_caller_is_current(usual_setup: Hand) -> None:
    hand = set_auction_to(
        bridge.contract.Bid(level=1, denomination=bridge.card.Suit.SPADES), usual_setup
    )

    caught_up = app.readers.get_xscript_updates(hand=hand, num_calls=4, num_plays=0)

    assert caught_up == {"calls": [], "plays": []}


# get_annotated_tricks


def test_annotated_tricks_describes_every_trick_of_a_played_out_hand(db: None) -> None:
    # Deliberately not the `usual_setup` fixture: it deals each player one whole
    # suit, so every trick is four different suits and nobody ever follows suit,
    # which would leave the bare-rank rule below untested.
    create_a_tournament(stage="playing", boards_per_round_per_table=1)
    a_hand = Hand.objects.first()
    assert a_hand is not None

    hand = _play_it_out(a_hand)

    tricks = app.readers.get_annotated_tricks(hand)

    assert len(tricks) == 13
    assert [t["number"] for t in tricks] == list(range(1, 14))

    for trick in tricks:
        assert len(trick["plays"]) == 4
        assert len([p for p in trick["plays"] if p["wins_the_trick"]]) == 1
        # Exactly one side won it.
        assert trick["ns"] != trick["ew"]

    # The lead carries its suit; a later card shows as a bare rank exactly when it
    # followed suit, and as a whole card when it did not. Count over every trick,
    # not just the first -- the first trick of this fixture happens to be four
    # different suits, which would make the comparison 0 == 0 and prove nothing.
    followed_suit = bare_ranks = 0

    for raw, annotated in zip(hand.get_xscript().tricks, tricks, strict=True):
        led_suit = raw.plays[0].card.suit
        followed_suit += len([p for p in raw.plays[1:] if p.card.suit == led_suit])

        assert hasattr(annotated["plays"][0]["card"], "suit"), "the lead should show its suit"
        bare_ranks += len(
            [p for p in annotated["plays"][1:] if not hasattr(p["card"], "suit")],
        )

    assert followed_suit > 0, "nobody ever followed suit, so this proves nothing"
    assert bare_ranks == followed_suit


# get_hand_status_string


def test_status_string_of_a_hand_still_being_played(usual_setup: Hand) -> None:
    assert app.readers.get_hand_status_string(usual_setup) == "…"


def test_status_string_of_a_completed_hand(usual_setup: Hand) -> None:
    hand = _play_it_out(usual_setup)

    assert hand.is_complete
    assert app.readers.get_hand_status_string(hand) == "✔"


def test_status_string_of_an_abandoned_hand(usual_setup: Hand) -> None:
    hand = usual_setup
    hand.abandoned_because = "the tournament expired out from under it"
    hand.save()

    assert app.readers.get_hand_status_string(hand) == "✘"


# get_hand_summary


def test_hand_summary_asks_an_anonymous_viewer_who_they_are(usual_setup: Hand) -> None:
    hand = usual_setup
    assert not hand.tournament.is_complete

    assert app.readers.get_hand_summary(hand=hand, as_viewed_by=None) == (
        "Remind me -- who are you, again?",
        "-",
    )


def test_hand_summary_of_an_unfinished_auction(usual_setup: Hand) -> None:
    hand = usual_setup
    viewer = hand.North

    assert app.readers.get_hand_summary(hand=hand, as_viewed_by=viewer) == (
        "Auction incomplete",
        "-",
    )


def test_hand_summary_scores_a_completed_hand_for_a_player_who_played_it(
    usual_setup: Hand,
) -> None:
    hand = _play_it_out(usual_setup)

    north_summary, north_score = app.readers.get_hand_summary(hand=hand, as_viewed_by=hand.North)
    east_summary, east_score = app.readers.get_hand_summary(hand=hand, as_viewed_by=hand.East)

    assert isinstance(north_score, int)
    assert isinstance(east_score, int)

    # The same result, scored from the two sides, comes out opposite.
    assert north_score == -east_score
    # Both sides read the same description; only the score takes a side.
    assert north_summary == east_summary
    assert "still being played" not in north_summary


def test_hand_summary_refuses_a_viewer_who_has_not_played_the_board(db: None) -> None:
    create_a_tournament(stage="playing", boards_per_round_per_table=1)

    # Two tables. Playing out the first board is what creates the second board's
    # hands, so this has to come before we can ask about board 2 at all.
    for hand in Hand.objects.filter(board__display_number=1):
        play_out_hand(hand)

    board_two_hands = list(Hand.objects.filter(board__display_number=2))
    assert len(board_two_hands) == 2

    played, not_played = board_two_hands
    play_out_hand(played)

    # This viewer is due to play the same board at another table, so they are not
    # allowed to see how it went here.
    viewer = not_played.North
    assert viewer.pk not in {p.pk for p in played.players_by_direction_letter.values()}

    summary, score = app.readers.get_hand_summary(hand=played, as_viewed_by=viewer)

    assert "have not completely played board" in summary
    assert score == "-"


# get_chat_disabled_explanation
#
# The "sign in with Google first" rules are exercised through the player detail
# view; these two cover the seated rules, which it never reaches.


def _oauth_verify(player: Player) -> Player:
    SocialAccount.objects.create(user=player.user, provider="google", uid=f"uid-{player.pk}")
    return player


def test_chat_is_disabled_when_the_recipient_has_not_signed_in_with_google(
    usual_setup: Hand,
) -> None:
    hand = usual_setup
    sender = _oauth_verify(hand.North)
    recipient = hand.East
    assert not recipient.is_oauth_verified

    explanation = app.readers.get_chat_disabled_explanation(sender=sender, recipient=recipient)

    assert explanation == (
        f"{recipient.name} hasn't signed in with Google, so you can't chat with them"
    )


def test_chat_is_disabled_when_the_recipient_is_seated(usual_setup: Hand) -> None:
    hand = usual_setup
    sender = _oauth_verify(hand.North)
    recipient = _oauth_verify(hand.East)

    explanation = app.readers.get_chat_disabled_explanation(sender=sender, recipient=recipient)

    assert explanation == f"{recipient.name} is already seated"


def test_chat_is_disabled_when_the_sender_is_seated(usual_setup: Hand) -> None:
    sender = _oauth_verify(usual_setup.North)
    recipient = _oauth_verify(Player.objects.create_synthetic())
    assert recipient.current_hand is None

    explanation = app.readers.get_chat_disabled_explanation(sender=sender, recipient=recipient)

    assert explanation == f"You, {sender.name}, are already seated"


# get_player_direction_at_hand


def test_direction_at_hand_of_a_player_who_was_never_there(usual_setup: Hand) -> None:
    stranger = Player.objects.create_synthetic()

    with pytest.raises(AssertionError, match="never played it"):
        app.readers.get_player_direction_at_hand(player=stranger, hand=usual_setup)
