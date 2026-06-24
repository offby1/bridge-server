import logging
from typing import Any

from django.contrib.syndication.views import Feed
from django.http import HttpRequest, HttpResponse
from django.urls import reverse

import app.models

logger = logging.getLogger(__name__)

# In compass order; each name is also the matching Hand FK attribute.
_SEATS = ("North", "East", "South", "West")


class CompletedTournamentsFeed(Feed):
    """An RSS feed of every hand played in a completed tournament.

    Hands belonging to tournaments that are still in progress are deliberately
    omitted; results only become public once a tournament is complete.
    """

    title = "Bridge: hands from completed tournaments"
    description = "Every hand played in a completed tournament, newest first."

    # The per-item body is rendered from a template; get_context_data() below
    # supplies it with the score line, the hand link, and the seated players.
    description_template = "feeds/hand_description.html"

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

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        hand: app.models.Hand = kwargs["item"]

        summary, score = hand.summary_as_viewed_by(as_viewed_by=None)
        context["score_line"] = summary if score in ("-", None) else f"{summary} ({score})"
        context["hand_url"] = self._abs("app:hand-dispatch", pk=hand.pk)
        context["seats"] = [
            {
                "direction": seat,
                "url": self._abs("app:player", pk=getattr(hand, seat).pk),
                "name": getattr(hand, seat).name,
            }
            for seat in _SEATS
        ]
        return context

    def item_pubdate(self, item: app.models.Hand):  # type: ignore[override]
        return item.board.tournament.completed_at
