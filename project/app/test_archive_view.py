from typing import Any

from django.contrib.auth.models import AnonymousUser

from .models import Hand
from .views.hand import _four_hands_context_for_hand


def test_archive_view(usual_setup: Hand, rf: Any) -> None:
    h = usual_setup
    request = rf.get("/woteva/", data={"pk": h.pk})
    request.user = AnonymousUser()
    # We're just testing for the absence of an exception
    _four_hands_context_for_hand(as_viewed_by=None, hand=h, as_dealt=True)
