from __future__ import annotations

import collections
from typing import Any

from django.contrib import auth

import pytest
from bridge.card import Card, Rank
from bridge.card import Suit as libSuit
from bridge.contract import Bid as libBid
from bridge.contract import Pass as libPass
from bridge.seat import Seat as libSeat
from bridge.table import Player as libPlayer

from .models import AuctionError, Board, Hand, Player, board, hand
from .testutils import set_auction_to

from .views.hand import (
    _bidding_box_context_for_hand,
    _bidding_box_HTML_for_hand_for_player,
)


def test_keeps_accurate_transcript(usual_setup: Hand) -> None:
    h = usual_setup
    set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), h)

    assert len(h.get_xscript().tricks) == 0

    declarer = h.declarer
    assert declarer is not None
    first_players_seat = declarer.seat.lho()
    first_player = h.players_by_direction_letter[first_players_seat.value]
    first_players_cards = first_player.dealt_cards()

    first_card = first_players_cards[0]

    h.add_play_from_model_player(player=first_player, card=first_card)
    h = Hand.objects.get(pk=h.pk)
    assert len(h.get_xscript().tricks) == 1
    first_trick = h.get_xscript().tricks[0]
    first_play = first_trick.plays[0]
    assert first_play.card == first_card

    # I don't check that the two player's *hands* are equal because the library is stupid
    assert first_play.seat == first_player.libraryThing().seat
    players_remaining_cards = h.players_remaining_cards(player=first_player.libraryThing()).cards
    assert players_remaining_cards is not None
    assert len(players_remaining_cards) == 12
    assert first_play.card not in players_remaining_cards


def test_rejects_illegal_calls(usual_setup: Hand) -> None:
    h = usual_setup

    caller = h.auction.allowed_caller()
    assert caller is not None

    def next_caller(current_caller):
        table = h.auction.table
        return table.get_lho(current_caller)

    h.add_call(call=libBid.deserialize("Pass"))

    caller = next_caller(caller)
    assert caller is not None

    one_notrump = libBid.deserialize("1N")
    assert one_notrump is not None

    h.add_call(call=one_notrump)

    caller = next_caller(caller)
    assert caller is not None

    with pytest.raises(AuctionError):
        h.add_call(call=libBid.deserialize("1N"))

    h.add_call(call=libBid.deserialize("Double"))

    calls = h.calls.all()

    assert "Pass" in str(calls[0])
    assert "one notrump" in str(calls[1])
    assert "Double" in str(calls[2])


def test_cards_by_player(usual_setup: Hand) -> None:
    h = usual_setup
    set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), h)
    assert h.auction.declarer is not None
    assert h.auction.declarer.seat == libSeat.NORTH

    east = Player.objects.get_by_name(name="Clint Eastwood")

    before = set(h.current_cards_by_seat()[libSeat.EAST])
    assert len(before) == 13  # just checkin' :-)

    diamond_two = Card(suit=libSuit.DIAMONDS, rank=Rank(2))
    h.add_play_from_model_player(player=east, card=diamond_two)
    h = Hand.objects.get(pk=h.pk)

    after = set(h.current_cards_by_seat()[libSeat.EAST])
    assert before - after == {diamond_two}
    for seat in (libSeat.NORTH, libSeat.SOUTH, libSeat.WEST):
        assert len(h.current_cards_by_seat()[seat]) == 13


def _bidding_box_as_seen_by(h: Hand, as_seen_by: Player | libPlayer, rf) -> str:
    from app.models.utils import assert_type

    if isinstance(as_seen_by, libPlayer):
        as_seen_by = Player.objects.get_by_name(as_seen_by.name)
    assert_type(as_seen_by, Player)
    assert isinstance(as_seen_by, Player)

    request = rf.get("/woteva/", data={"hand_pk": h.pk})
    request.user = as_seen_by.user

    return _bidding_box_HTML_for_hand_for_player(h, as_seen_by)


def _partition_button_values(bb_html: str) -> tuple[list[str], list[str]]:
    disabled_buttons: list[str] = []
    active_buttons: list[str] = []
    bb_html_lines = bb_html.split("\n")

    def value(html: str) -> str:
        import re

        m = re.search(r'value="(.*?)"', html)
        assert m is not None, html
        return m.group(1)

    for line in bb_html_lines:
        if "<button" not in line:
            continue
        if " disabled" in line:
            disabled_buttons.append(value(line))
        else:
            active_buttons.append(value(line))

    return disabled_buttons, active_buttons


def test_bidding_box_html_completed_auction(usual_setup: Hand, rf) -> None:
    h = usual_setup

    # First case: completed auction, contract is one diamond, not doubled.
    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), h)
    # set_auction_to has set the declarer to be the dealer.

    assert h.auction.found_contract

    # The auction is settled, so no bidding box.
    assert h.player_who_may_play is not None
    bb_str = _bidding_box_as_seen_by(h, h.player_who_may_play, rf)

    # TODO -- actually parse the HTML; look for a div whose id is #bidding-box, and assert that *either*
    # - there is no such div; or else
    # - it's empty
    assert "btn-primary" not in bb_str


def test_bidding_box_html_one_call(usual_setup: Hand, rf) -> None:
    h = usual_setup

    # Second case: auction in progress, only call is one diamond.
    allowed_caller = h.auction.allowed_caller()
    assert allowed_caller is not None
    assert allowed_caller.name == "Jeremy Northam"

    from app.models import logged_queries

    allowed_caller = h.auction.allowed_caller()
    assert allowed_caller is not None

    h.add_call(
        call=libBid(level=1, denomination=libSuit.DIAMONDS),
    )

    with logged_queries():
        allowed_caller = h.auction.allowed_caller()
        assert allowed_caller is not None
        assert allowed_caller.name == "Clint Eastwood"

    east = Player.objects.get_by_name("Clint Eastwood")
    request = rf.get("/woteva/")
    request.user = east.user
    bbc_html = _bidding_box_context_for_hand(as_viewed_by=request.user.player, hand=h)[
        "bidding_box_buttons"
    ]
    disabled, _active = _partition_button_values(bbc_html)
    assert set(disabled) == {"1♣", "1♦", "Redouble"}


def test_bidding_box_html_two_calls(usual_setup: Hand, rf) -> None:
    h = usual_setup
    # Third case: as above but with one more "Pass".

    def ac() -> libPlayer:
        rv = h.auction.allowed_caller()
        assert rv is not None
        return rv

    h.add_call(
        call=libBid(level=1, denomination=libSuit.DIAMONDS),
    )
    h.add_call(
        call=libPass,
    )

    allowed_caller = h.auction.allowed_caller()
    assert allowed_caller is not None
    assert allowed_caller.name == "J.D. Souther"

    south = Player.objects.get_by_name("J.D. Souther")
    request = rf.get("/woteva/", data={"hand_pk": h.pk})
    request.user = south.user
    bbc_html = _bidding_box_context_for_hand(as_viewed_by=request.user.player, hand=h)[
        "bidding_box_buttons"
    ]
    # you cannot double your own partner.
    disabled, _active = _partition_button_values(bbc_html)

    assert set(disabled) == {
        "1♣",
        "1♦",
        "Double",
        "Redouble",
    }
    east = Player.objects.get_by_name("Clint Eastwood")
    request.user = east.user
    bbc_html = _bidding_box_context_for_hand(as_viewed_by=request.user.player, hand=h)[
        "bidding_box_buttons"
    ]

    disabled, _active = _partition_button_values(bbc_html)
    assert len(disabled) == 38, f"{east} shouldn't be allowed to call at all"


def test_current_trick(usual_setup: Hand) -> None:
    h = usual_setup
    # Nobody done played nothin'
    assert not h.current_trick

    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), h)
    libDeclarer = h.declarer
    assert libDeclarer is not None
    # TODO -- add a "lho" method to model.Player
    first_players_seat = libDeclarer.seat.lho()
    first_player = h.players_by_direction_letter[first_players_seat.value]
    first_players_cards = first_player.dealt_cards()

    dummy = h.model_dummy
    assert dummy is not None
    dummys_cards = dummy.dealt_cards()

    first_card = first_players_cards[0]
    h.add_play_from_model_player(player=first_player, card=first_card)

    assert h.current_trick is not None
    assert len(h.current_trick) == 1
    tt = h.current_trick[-1]
    assert tt.card == first_card

    second_card = dummys_cards[0]
    model_declarer = h.model_declarer
    assert model_declarer is not None
    h.add_play_from_model_player(player=model_declarer, card=second_card)

    assert len(h.current_trick) == 2
    tt = h.current_trick[-1]
    assert tt.card == second_card


def test_next_seat_to_play(usual_setup: Hand) -> None:
    h = usual_setup

    assert h.next_seat_to_play is None, "There's been no auction, so nobody can play"

    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), h)

    assert h.declarer is not None
    assert h.declarer.seat == libSeat.NORTH
    assert h.next_seat_to_play is not None
    assert h.next_seat_to_play.name == "East"


def test_sends_message_on_auction_completed(usual_setup: Hand, monkeypatch) -> None:
    h = usual_setup

    sent_events_by_channel: dict[str, list[Any]] = collections.defaultdict(list)

    def send_event(*, channel, event_type, data):
        sent_events_by_channel[channel].append(data)

    monkeypatch.setattr(hand, "send_event", send_event)
    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), h)

    first_player = Player.objects.first()
    assert first_player is not None
    assert any("contract" in e for e in sent_events_by_channel[f"player:json:{first_player.pk}"])
    assert any("contract" in e for e in sent_events_by_channel[f"table:html:{h.pk}"])


@pytest.mark.django_db
def test_predictable_shuffles():
    attrs1_empty = board.board_attributes_from_display_number(display_number=1, rng_seeds=[])
    attrs2_empty = board.board_attributes_from_display_number(display_number=2, rng_seeds=[])

    # Same  'cuz we used the same random seeds
    for k in ("north_cards", "east_cards", "south_cards", "west_cards"):
        assert attrs1_empty[k] == attrs2_empty[k]

    attrs1_golly = board.board_attributes_from_display_number(
        display_number=1, rng_seeds=[b"golly"]
    )

    for k in ("ns_vulnerable", "ew_vulnerable", "dealer"):
        assert attrs1_empty[k] == attrs1_golly[k]

    # Cards are different
    for k in ("north_cards", "east_cards", "south_cards", "west_cards"):
        assert attrs1_empty[k] != attrs1_golly[k]


def test_is_abandoned_splitsville(usual_setup, everybodys_password) -> None:
    assert Hand.objects.count() > 0

    for h in Hand.objects.all():
        assert not h.is_abandoned

    h = Hand.objects.first()
    assert h is not None
    assert not h.is_complete

    for dir_ in h.direction_names:
        assert getattr(h, dir_, None) is not None

    north: Player | None = h.North
    assert north is not None

    south: Player | None = north.partner
    assert south is not None

    north.break_partnership()
    assert not north.currently_seated
    assert not south.currently_seated

    h = Hand.objects.get(pk=h.pk)
    assert h.is_abandoned

    message = h.abandoned_because
    assert "left" in message
    assert north.name in message or south.name in message


@pytest.mark.skip(reason="I suspect this is pointless")
def test_is_abandoned_defection(usual_setup, everybodys_password) -> None:
    h = Hand.objects.first()
    assert h is not None

    north: Player | None = h.North
    assert north is not None

    south: Player | None = north.partner
    assert south is not None

    # Now put north and south into some other hand
    new_player_names = ["e2", "w2"]
    for name in new_player_names:
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )

    Player.objects.get_by_name("e2").partner_with(Player.objects.get_by_name("w2"))

    board, _ = Board.objects.get_or_create_from_display_number(
        display_number=Board.objects.count() + 1,
        group="A",
        tournament=h.board.tournament,
    )
    Hand.objects.create(
        board=board,
        North=north,
        East=Player.objects.get_by_name("e2"),
        South=south,
        West=Player.objects.get_by_name("w2"),
        table_display_number=h.table_display_number,
    )

    h = Hand.objects.get(pk=h.pk)
    assert h.is_abandoned

    message = h.abandoned_because

    assert north.name in message or south.name in message
    assert "defected, those bastards" in message
