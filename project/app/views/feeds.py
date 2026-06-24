import logging

from django.contrib.syndication.views import Feed
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils.html import format_html, format_html_join

import app.models

logger = logging.getLogger(__name__)

# In compass order, paired with the matching Hand FK attribute name.
_SEATS = ("North", "East", "South", "West")


class CompletedTournamentsFeed(Feed):
    """An RSS feed of every hand played in a completed tournament.

    Hands belonging to tournaments that are still in progress are deliberately
    omitted; results only become public once a tournament is complete.
    """

    title = "Bridge: hands from completed tournaments"
    description = "Every hand played in a completed tournament, newest first."

    def __call__(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        # Stash the request so the item_* methods can build absolute URLs that
        # point at whatever host the feed was fetched from (e.g. localhost in
        # development) rather than the django.contrib.sites domain.
        self.request = request
        return super().__call__(request, *args, **kwargs)

    def _abs(self, viewname: str, **kwargs) -> str:
        return self.request.build_absolute_uri(reverse(viewname, kwargs=kwargs))

    def link(self) -> str:
        return self._abs("app:tournament-list")

    def items(self) -> list[app.models.Hand]:
        return list(
            app.models.Hand.objects.filter(board__tournament__completed_at__isnull=False)
            .select_related(
                "board",
                "board__tournament",
                *(f"{seat}__user" for seat in _SEATS),
            )
            .order_by(
                "-board__tournament__completed_at",
                "table_display_number",
                "board__display_number",
            )
        )

    def item_title(self, item: app.models.Hand) -> str:  # type: ignore[override]
        return f"{item.board.short_string()} at table #{item.table_display_number}"

    def item_link(self, item: app.models.Hand) -> str:  # type: ignore[override]
        return self._abs("app:hand-dispatch", pk=item.pk)

    def item_description(self, item: app.models.Hand) -> str:  # type: ignore[override]
        summary, score = item.summary_as_viewed_by(as_viewed_by=None)
        score_line = summary if score in ("-", None) else f"{summary} ({score})"

        seats = format_html_join(
            "\n",
            '<li>{}: <a href="{}">{}</a></li>',
            (
                (direction, self._abs("app:player", pk=player.pk), player.name)
                for direction, player in ((seat, getattr(item, seat)) for seat in _SEATS)
            ),
        )

        return format_html(
            '<p>{}</p>\n<p><a href="{}">View this hand</a></p>\n<ul>\n{}\n</ul>',
            score_line,
            self._abs("app:hand-dispatch", pk=item.pk),
            seats,
        )

    def item_pubdate(self, item: app.models.Hand):  # type: ignore[override]
        return item.board.tournament.completed_at
