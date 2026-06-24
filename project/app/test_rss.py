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

    # Each item's description links to the hand and lists the four players by
    # compass position, with each name linking to that player.
    descriptions_by_link = {
        item.findtext("link"): item.findtext("description") or ""
        for item in channel.findall("item")
    }
    for h in complete_hands:
        hand_link = reverse("app:hand-dispatch", kwargs={"pk": h.pk})
        desc = next(d for il, d in descriptions_by_link.items() if il and hand_link in il)

        assert hand_link in desc, f"hand {h.pk}'s description should link to the hand"

        for direction in ("North", "East", "South", "West"):
            player = getattr(h, direction)
            player_link = reverse("app:player", kwargs={"pk": player.pk})
            assert direction in desc, f"missing compass position {direction} for hand {h.pk}"
            assert player_link in desc, f"missing link to {player.name} for hand {h.pk}"
            assert player.name in desc, f"missing name {player.name} for hand {h.pk}"
