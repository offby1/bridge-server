from bridge.card import Suit
from bridge.contract import Bid

from .models import Player, Table
from .testutils import set_auction_to
from .views.hand import hand_list_view


def test_for_more_smoke(usual_setup, rf) -> None:
    t: Table | None = Table.objects.first()
    assert t is not None

    t = set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)

    # all players have just one suit, so it's easy to play all the cards
    while True:
        assert t is not None
        legal_cards = t.current_hand.xscript.legal_cards()
        if not legal_cards:
            break
        chosen_card = legal_cards[0]

        t.current_hand.add_play_from_player(player=t.current_hand.xscript.player, card=chosen_card)
        t = Table.objects.get(pk=t.pk)

    request = rf.get("/woteva/")
    north = Player.objects.get_by_name("Jeremy Northam")
    request.user = north.user
    response = hand_list_view(request)
    print(response.content.decode())
    assert "cat" == "dog"
