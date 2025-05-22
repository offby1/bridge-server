from typing import Any


from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command

from app.models import Hand

from app.views.hand import _four_hands_context_for_hand, hand_archive_view


def test_archive_view(usual_setup: Hand, rf: Any) -> None:
    h = usual_setup
    request = rf.get("/woteva/", data={"pk": h.pk})
    request.user = AnonymousUser()
    # We're just testing for the absence of an exception
    _four_hands_context_for_hand(request=request, hand=h, as_dealt=True)


# Load 2025-05-22T19:43:52+0000.sql, log in as admin/admin, browse to http://localhost:9000/hand/10/archive/
def test_something_else(db, rf):
    call_command("loaddata", "smoke-case-1")
    hand_pk = 10
    request = rf.get("/woteva/", data={"pk": hand_pk})
    request.user = User.objects.get(username="admin")

    hand_archive_view(request=request, pk=hand_pk)
