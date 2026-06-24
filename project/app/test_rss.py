# Create one complete, and one incomplete, tournament
# fetch /tournaments.rss/
# ensure it's 2xx
# ensure it's proper RSS
# ensure it contains all the hands from the complete tournament, and nothing from the incomplete tournament

from xml.etree import ElementTree

from django.urls import reverse

from app.models import Hand

from .testutils import create_a_tournament


def test_tournaments_rss_feed(db, client) -> None:
    complete = create_a_tournament(stage="complete")
    incomplete = create_a_tournament(stage="playing")

    complete_hands = list(complete.hands())
    incomplete_hands = list(incomplete.hands())
    assert complete_hands, "the complete tournament should have hands"
    assert incomplete_hands, "the incomplete tournament should have hands"

    response = client.get(reverse("app:tournaments-rss"))

    # 2xx
    assert response.status_code == 200
    assert "rss" in response["Content-Type"] or "xml" in response["Content-Type"]

    # proper RSS: parses as XML, is an <rss> document with a <channel>
    root = ElementTree.fromstring(response.content)
    assert root.tag == "rss"
    channel = root.find("channel")
    assert channel is not None

    item_links = {item.findtext("link") for item in channel.findall("item")}

    # every hand from the complete tournament is present...
    for h in complete_hands:
        link = reverse("app:hand-dispatch", kwargs={"pk": h.pk})
        assert any(link in il for il in item_links if il is not None), (
            f"hand {h.pk} from the completed tournament is missing from the feed"
        )

    # ...and no hand from the incomplete tournament leaks in.
    for h in incomplete_hands:
        link = reverse("app:hand-dispatch", kwargs={"pk": h.pk})
        assert not any(link in il for il in item_links if il is not None), (
            f"hand {h.pk} from the incomplete tournament should not be in the feed"
        )

    # The feed item count matches exactly the completed tournament's hands.
    assert (
        len(channel.findall("item"))
        == Hand.objects.filter(board__tournament__completed_at__isnull=False).count()
    )
