from typing import Any


from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command

from app.models import Hand, Player

from app.views.hand import _four_hands_context_for_hand, hand_archive_view


def test_archive_view(usual_setup: Hand, rf: Any) -> None:
    h = usual_setup
    request = rf.get("/woteva/", data={"pk": h.pk})
    request.user = AnonymousUser()
    # We're just testing for the absence of an exception
    _four_hands_context_for_hand(request=request, hand=h, as_dealt=True)


# Load 2025-05-22T19:43:52+0000.sql, log in as admin/admin, browse to http://localhost:9000/hand/10/archive/
def test_something_else(db: Any, rf: Any) -> None:
    call_command("loaddata", "smoke-case-1")
    hand_pk = 10
    request = rf.get("/woteva/", data={"pk": hand_pk})

    hand = Hand.objects.get(pk=hand_pk)

    # Various flavors of user
    has_no_player = User.objects.get(username="admin")
    played_the_hand = hand.players().first().user
    did_not_play_the_hand = Player.objects.create_synthetic().user

    for user in (None, has_no_player, played_the_hand, did_not_play_the_hand):
        request.user = user
        hand_archive_view(request=request, pk=hand_pk)
