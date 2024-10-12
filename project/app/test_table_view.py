from bridge.card import Card, Suit
from bridge.contract import Bid
from bridge.seat import Seat
from django.contrib import auth

from .models import Player, Table
from .testutils import set_auction_to
from .views.hand import _display_and_control


def test_table_dataclass_thingy(usual_setup: None) -> None:
    t = Table.objects.first()
    assert t is not None
    t = set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)
    assert t.current_auction.declarer.seat == Seat.NORTH

    ds = t.current_hand.display_skeleton()
    for dir_ in Seat:
        assert ds[dir_].textual_summary == "13 cards"

    assert not ds[Seat.NORTH].this_hands_turn_to_play
    assert ds[Seat.EAST].this_hands_turn_to_play
    assert not ds[Seat.SOUTH].this_hands_turn_to_play
    assert not ds[Seat.WEST].this_hands_turn_to_play


def test_hand_visibility(usual_setup: None, settings, everybodys_password) -> None:
    t1 = Table.objects.first()
    assert t1 is not None
    t1 = set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t1)

    assert str(t1.current_auction.status) == "one Club played by Jeremy Northam, sitting North"

    new_player_names = ["n2", "e2", "s2", "w2"]
    for name in new_player_names:
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )

    Player.objects.get_by_name("n2").partner_with(Player.objects.get_by_name("s2"))
    Player.objects.get_by_name("e2").partner_with(Player.objects.get_by_name("w2"))

    t2 = Table.objects.create_with_two_partnerships(
        p1=Player.objects.get_by_name("n2"),
        p2=Player.objects.get_by_name("e2"),
        shuffle_deck=False,
    )

    t2.next_board()
    t2 = set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t2)

    def expect_visibility(expectation_array):
        for seat in t1.current_hand.players_by_direction:
            for viewer in t1.current_hand.players_by_direction:
                actual1 = _display_and_control(
                    hand=t1.current_hand,
                    seat=Seat(seat),
                    as_viewed_by=t1.current_hand.players_by_direction[viewer],
                    as_dealt=False,
                )
                assert (
                    actual1["display_cards"] == expectation_array[seat - 1][viewer - 1]
                ), f"{t1.current_hand.players_by_direction[viewer]} {'can' if actual1['display_cards'] else 'can not'} see {seat=} "

                actual2 = _display_and_control(
                    hand=t2.current_hand,
                    seat=Seat(seat),
                    as_viewed_by=t1.current_hand.players_by_direction[viewer],
                    as_dealt=False,
                )
                assert (
                    actual2["display_cards"] is False
                ), "wtf -- player at table 1 can see cards at table 2??"

    expect_visibility(
        [
            # n, e, s, w
            [1, 0, 0, 0],  # n
            [0, 1, 0, 0],  # e
            [0, 0, 1, 0],  # s
            [0, 0, 0, 1],  # w
        ]
    )

    # Make the opening lead
    t1.current_hand.add_play_from_player(
        player=t1.current_hand.players_by_direction[Seat.EAST.value].libraryThing,
        card=Card.deserialize("D2"),
    )
    t1 = Table.objects.first()

    # Now the dummy (south) is visible
    expect_visibility(
        [
            # n, e, s, w <-- viewers
            [1, 0, 0, 0],  # n seat
            [0, 1, 0, 0],  # e
            [1, 1, 1, 1],  # s
            [0, 0, 0, 1],  # w
        ]
    )

    # play out the hand
    while True:
        legal_cards = t1.current_hand.xscript.legal_cards()
        if not legal_cards:
            break
        chosen_card = legal_cards[0]

        t1.current_hand.add_play_from_player(
            player=t1.current_hand.xscript.player, card=chosen_card
        )
        t1 = Table.objects.get(pk=t1.pk)

    expect_visibility(
        [
            # n, e, s, w <-- viewers
            [1, 1, 1, 1],  # n seat
            [1, 1, 1, 1],  # e
            [1, 1, 1, 1],  # s
            [1, 1, 1, 1],  # w
        ]
    )


def test_hand_controlability(usual_setup: None, settings) -> None:
    t = Table.objects.first()
    assert t is not None

    def expect_controlability(expectation_array):
        for seat in t.current_hand.players_by_direction:
            for viewer in t.current_hand.players_by_direction:
                actual = _display_and_control(
                    hand=t.current_hand,
                    seat=Seat(seat),
                    as_viewed_by=t.current_hand.players_by_direction[viewer],
                    as_dealt=False,
                )
                assert (
                    actual["viewer_may_control_this_seat"]
                    == expectation_array[seat - 1][viewer - 1]
                ), f"{t.current_hand.players_by_direction[viewer]} {'can' if actual['viewer_may_control_this_seat'] else 'can not'} control {seat=} "

    # Nobody can control any cards, since the auction isn't settled
    expect_controlability(
        [
            # n, e, s, w
            [0, 0, 0, 0],  # n
            [0, 0, 0, 0],  # e
            [0, 0, 0, 0],  # s
            [0, 0, 0, 0],  # w
        ]
    )

    t = set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)
    assert str(t.current_hand.auction.status) == "one Club played by Jeremy Northam, sitting North"

    # Only opening leader can control his cards
    expect_controlability(
        [
            # n, e, s, w
            [0, 0, 0, 0],  # n
            [0, 1, 0, 0],  # e
            [0, 0, 0, 0],  # s
            [0, 0, 0, 0],  # w
        ]
    )

    # Make the opening lead
    t.current_hand.add_play_from_player(
        player=t.current_hand.players_by_direction[Seat.EAST.value].libraryThing,
        card=Card.deserialize("D2"),
    )
    t = Table.objects.first()

    # Now declarer (north) can control the dummy (south).  (TODO -- what if the dummy is a bot?)
    expect_controlability(
        [
            # n, e, s, w <-- viewers
            [0, 0, 0, 0],  # n seat
            [0, 0, 0, 0],  # e
            [1, 0, 0, 0],  # s
            [0, 0, 0, 0],  # w
        ]
    )
