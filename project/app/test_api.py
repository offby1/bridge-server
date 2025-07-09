import django.db.models
from django.test import Client
from django.urls import reverse

import bridge.card
import bridge.contract

from app.models import Board, Call, Hand, Play, Player, Tournament
from .testutils import set_auction_to


def test_xscript_works_despite_caching_being_hard_yo(usual_setup) -> None:
    h1 = Hand.objects.first()
    assert h1 is not None

    assert len(h1.get_xscript().auction.player_calls) == 0

    c = Call.objects.create(serialized="1♣", hand=h1)
    c.save()

    assert len(h1.get_xscript().auction.player_calls) == 1

    Call.objects.create(serialized="Pass", hand=h1)
    Call.objects.create(serialized="Pass", hand=h1)
    Call.objects.create(serialized="Pass", hand=h1)

    assert len(h1.get_xscript().auction.player_calls) == 4

    assert list(h1.get_xscript().plays()) == []

    Play.objects.create(serialized="♦2", hand=h1)

    plays = list(h1.get_xscript().plays())
    assert len(plays) == 1
    assert plays[0].card.serialize() == "♦2"


def _no_voids():
    deck = bridge.card.Card.deck()

    north_cards = []
    east_cards = []
    south_cards = []
    west_cards = []

    while deck:
        north_cards.append(str(deck.pop()))
        east_cards.append(str(deck.pop()))
        south_cards.append(str(deck.pop()))
        west_cards.append(str(deck.pop()))

    board = Board.objects.create(
        **{
            "dealer": "N",
            "display_number": 1
            + Board.objects.all().aggregate(django.db.models.Max("display_number"))[
                "display_number__max"
            ],
            "east_cards": "".join(east_cards),
            "ew_vulnerable": False,
            "north_cards": "".join(north_cards),
            "ns_vulnerable": True,
            "south_cards": "".join(south_cards),
            "tournament": Tournament.objects.first(),
            "west_cards": "".join(west_cards),
        }
    )
    existing_hand = Hand.objects.first()

    for p in existing_hand.players():
        p.current_hand = None
        p.save()

    return Hand.objects.create(
        board=board,
        **{d: getattr(existing_hand, d) for d in existing_hand.direction_names},
        table_display_number=12345,
    )


def test_play_post_view(usual_setup, rf):
    c = Client()

    # Anonymous user
    response = c.post(reverse("app:play-post"), data={"card": "C2"})

    assert response.status_code == 302
    assert "/accounts/login/?next=/play/" in response.url

    hand = Hand.objects.first()
    set_auction_to(bridge.contract.Bid(level=1, denomination=bridge.card.Suit.CLUBS), hand)

    # Not seated
    player, _ = Player.objects.get_or_create_synthetic()
    c.force_login(player.user)
    response = c.post(reverse("app:play-post"), data={"card": "C2"})
    assert response.status_code == 403
    assert "not currently seated" in response.text

    # Seated, but not my turn
    player = Player.objects.exclude(pk=hand.player_who_may_play.pk).first()
    assert player != hand.player_who_may_play
    c.force_login(player.user)

    assert hand.player_who_may_play.name == "Clint Eastwood"
    east_cards_string = getattr(hand.board, "east_cards")

    response = c.post(reverse("app:play-post"), data={"card": east_cards_string[0:2]})
    assert response.status_code == 403
    assert "turn to play" in response.text

    # My turn, but not a valid card string
    c.force_login(hand.player_who_may_play.user)
    response = c.post(
        reverse("app:play-post"), data={"card": "not really a serialized card at all"}
    )
    assert response.status_code == 403
    assert "Cannot deserialize" in response.text

    # My turn, but not my card
    north_cards_string = getattr(hand.board, "north_cards")
    response = c.post(
        reverse("app:play-post"),
        data={"card": north_cards_string[0:2]},
        headers={"accept": "application/json"},
    )
    assert response.status_code == 403
    assert "don't hold" in response.text

    # One that works
    assert hand.player_who_may_play.name == "Clint Eastwood"
    c.force_login(hand.player_who_may_play.user)
    response = c.post(reverse("app:play-post"), data={"card": east_cards_string[0:2]})
    assert response.status_code == 200

    # right player, and their card; but illegal because it's not following suit
    hand: Hand = _no_voids()
    set_auction_to(bridge.contract.Bid(level=1, denomination=bridge.card.Suit.CLUBS), hand)
    assert hand.player_who_may_play.name == "Clint Eastwood"
    c.force_login(hand.player_who_may_play.user)

    response = c.post(reverse("app:play-post"), data={"card": "C4"})
    assert response.status_code == 200

    declarer = hand.player_who_controls_seat(hand.next_seat_to_play)
    assert declarer.name == "Jeremy Northam"

    c.force_login(declarer.user)

    response = c.post(reverse("app:play-post"), data={"card": "D2"})
    assert response.status_code == 403
    assert "cannot play" in response.text
