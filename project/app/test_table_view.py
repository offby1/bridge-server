from bridge.card import Card, Suit
from bridge.contract import Bid
from bridge.seat import Seat
from django.contrib.auth.models import AnonymousUser

from .models import Table
from .testutils import set_auction_to
from .views.table.details import _display_and_control, _four_hands_context_for_table


def test_table_dataclass_thingy(usual_setup: None) -> None:
    t = Table.objects.first()
    assert t is not None
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)
    assert t.current_auction.declarer.seat == Seat.NORTH

    ds = t.display_skeleton()
    for dir_ in Seat:
        assert ds[dir_].textual_summary == "13 cards"

    assert not ds[Seat.NORTH].this_hands_turn_to_play
    assert ds[Seat.EAST].this_hands_turn_to_play
    assert not ds[Seat.SOUTH].this_hands_turn_to_play
    assert not ds[Seat.WEST].this_hands_turn_to_play


def test_hand_visibility(usual_setup: None, settings) -> None:
    t = Table.objects.first()
    assert t is not None
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)
    assert str(t.current_auction.status) == "one Club played by Jeremy Northam, sitting North"

    settings.POKEY_BOT_BUTTONS = False

    def expect_visibility(expecation_array):
        for seat in t.players_by_direction:
            for viewer in t.players_by_direction:
                actual = _display_and_control(
                    table=t,
                    seat=Seat(seat),
                    as_viewed_by=t.players_by_direction[viewer],
                    as_dealt=False,
                )
                assert (
                    actual["display_cards"] == expecation_array[seat - 1][viewer - 1]
                ), f"{t.players_by_direction[viewer]} {'can' if actual['display_cards'] else 'can not'} see {seat=} "

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
    t.current_hand.add_play_from_player(
        player=t.players_by_direction[Seat.EAST.value].libraryThing, card=Card.deserialize("D2")
    )

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


def test_hand_controlability(usual_setup: None, settings) -> None:
    t = Table.objects.first()
    assert t is not None

    def expect_controlability(expecation_array):
        for seat in t.players_by_direction:
            for viewer in t.players_by_direction:
                actual = _display_and_control(
                    table=t,
                    seat=Seat(seat),
                    as_viewed_by=t.players_by_direction[viewer],
                    as_dealt=False,
                )
                assert (
                    actual["viewer_may_control_this_seat"] == expecation_array[seat - 1][viewer - 1]
                ), f"{t.players_by_direction[viewer]} {'can' if actual['viewer_may_control_this_seat'] else 'can not'} control {seat=} "

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

    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)
    assert str(t.current_auction.status) == "one Club played by Jeremy Northam, sitting North"

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
        player=t.players_by_direction[Seat.EAST.value].libraryThing, card=Card.deserialize("D2")
    )

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


def test_archive_view(usual_setup, rf):
    t = Table.objects.first()
    request = rf.get("/woteva/", data={"pk": t.pk})
    request.user = AnonymousUser()
    # We're just testing for the absence of an exception
    _four_hands_context_for_table(request, t, as_dealt=True)
