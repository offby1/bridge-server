from typing import Any


from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command

from app.models import Hand, Player

from app.views.hand import hand_archive_view, hand_detail_view


def test_both_important_views(db: Any, rf: Any) -> None:
    call_command("loaddata", "smoke-case-1")
    hand_pk = 10
    request = rf.get("/woteva/", data={"pk": hand_pk})

    hand = Hand.objects.get(pk=hand_pk)

    # Various flavors of user
    anonymoose = AnonymousUser()
    has_no_player = User.objects.get(username="admin")
    played_the_hand = hand.players().first().user
    did_not_play_the_hand = Player.objects.create_synthetic().user

    for user in (None, anonymoose, has_no_player, played_the_hand, did_not_play_the_hand):
        request.user = user
        hand_archive_view(request=request, pk=hand_pk)
        hand_detail_view(request=request, pk=hand_pk)
