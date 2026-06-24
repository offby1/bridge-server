import logging

from django.contrib.syndication.views import Feed
from django.urls import reverse

import app.models

logger = logging.getLogger(__name__)


class CompletedTournamentsFeed(Feed):
    """An RSS feed of every hand played in a completed tournament.

    Hands belonging to tournaments that are still in progress are deliberately
    omitted; results only become public once a tournament is complete.
    """

    title = "Bridge: hands from completed tournaments"
    description = "Every hand played in a completed tournament, newest first."

    def link(self) -> str:
        return reverse("app:tournament-list")

    def items(self) -> list[app.models.Hand]:
        return list(
            app.models.Hand.objects.filter(board__tournament__completed_at__isnull=False)
            .select_related("board", "board__tournament")
            .order_by(
                "-board__tournament__completed_at",
                "table_display_number",
                "board__display_number",
            )
        )

    # django-stubs types these overrides with a `Model` item; we intentionally
    # narrow to Hand (and item_title returns a plain str rather than SafeText).
    def item_title(self, item: app.models.Hand) -> str:  # type: ignore[override]
        return f"{item.board.short_string()} at table #{item.table_display_number}"

    def item_description(self, item: app.models.Hand) -> str:  # type: ignore[override]
        summary, score = item.summary_as_viewed_by(as_viewed_by=None)
        if score in ("-", None):
            return summary
        return f"{summary} ({score})"

    def item_link(self, item: app.models.Hand) -> str:  # type: ignore[override]
        return reverse("app:hand-dispatch", kwargs={"pk": item.pk})

    def item_pubdate(self, item: app.models.Hand):  # type: ignore[override]
        return item.board.tournament.completed_at
