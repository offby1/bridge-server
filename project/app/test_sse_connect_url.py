"""Guard the URL of the page's single SSE connection.

Pages declare the channels they need by overriding the `sse_channels_query` block, and
that block's output lands inside the `sse-connect` attribute on `<body>`. Anything that
puts the block's content on its own line -- djLint's formatter will, given the chance --
injects a newline and indentation into the middle of a query string, so `?hand=1`
becomes `?%0A%20%20%20%20hand=1` and the server sees a parameter named "\\n    hand".

Nothing else would notice. The page renders, the connection opens, and the viewer simply
never receives table updates. So assert on the attribute directly.
"""

import re

import pytest
from django.test import Client
from django.urls import reverse

from app.models import Hand, Player

SSE_CONNECT = re.compile(r'sse-connect="([^"]*)"')


def _sse_connect_url(html: str) -> str:
    match = SSE_CONNECT.search(html)
    assert match is not None, "No sse-connect attribute; did <body> lose the connection?"
    return match.group(1)


@pytest.fixture
def logged_in_client(usual_setup: Hand) -> Client:
    player = Player.objects.first()
    assert player is not None
    client = Client()
    client.force_login(player.user)
    return client


def test_the_hand_page_asks_for_its_table(logged_in_client: Client, usual_setup: Hand) -> None:
    hand = usual_setup
    response = logged_in_client.get(reverse("app:hand-dispatch", kwargs={"pk": hand.pk}))
    assert response.status_code == 200

    assert _sse_connect_url(response.content.decode()) == f"/events/all/?hand={hand.pk}"


def test_a_finished_hand_opens_no_connection(logged_in_client: Client, usual_setup: Hand) -> None:
    """Nothing will ever be sent about a hand that's over, so don't spend a socket on it.

    Reviewing a dozen finished hands in a dozen tabs used to exhaust the browser's six
    connections and leave most of the tabs spinning.
    """
    hand = usual_setup
    hand.abandoned_because = "so that this hand is over"
    hand.save()

    response = logged_in_client.get(reverse("app:hand-dispatch", kwargs={"pk": hand.pk}))
    assert response.status_code == 200

    body = response.content.decode()
    assert SSE_CONNECT.search(body) is None, "A finished hand should not open a connection"
    # base.html's script keys off the attribute's presence, so it skips creating the
    # connection; its own handlers sit inside that guard and never run. But this page's
    # 'table' listener is emitted separately, and would reference an object that doesn't
    # exist.
    assert "addEventListener('table'" not in body


def test_the_connection_url_contains_no_whitespace(
    logged_in_client: Client, usual_setup: Hand
) -> None:
    """The failure this file exists for: a reformatted template block."""
    hand = usual_setup
    response = logged_in_client.get(reverse("app:hand-dispatch", kwargs={"pk": hand.pk}))

    url = _sse_connect_url(response.content.decode())
    assert not re.search(r"\s", url), (
        f"Whitespace in {url!r}. The sse_channels_query block was probably reformatted "
        f"onto its own line; the djlint:off comments around it exist to prevent that."
    )
