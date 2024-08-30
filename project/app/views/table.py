from __future__ import annotations

import collections

import bridge.card
import bridge.contract
from app.models import Player, Table
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.views.decorators.http import require_http_methods

from .misc import logged_in_as_player_required


def table_list_view(request):
    context = {
        "table_list": Table.objects.all(),
    }

    return TemplateResponse(request, "table_list.html", context=context)


def _bidding_box(table):
    def buttonize(call):
        return f"""
        <button type="button"
        class="btn btn-primary" {"" if active else "disabled"}>
        {call}
        </button>
        """

    calls_by_level = collections.defaultdict(list)

    for call in bridge.contract.Bid.all_exceeding():
        calls_by_level[call.level].append(call)

    mrb = None
    if table.current_handrecord.most_recent_bid is not None:
        mrb = table.current_handrecord.most_recent_bid.libraryCall

    rows = []
    for calls in calls_by_level.values():
        row = '<div class="btn-group">'

        buttons = []
        for c in calls:
            active = mrb is None or c > mrb

            buttons.append(buttonize(c))

        row += "".join(buttons)

        row += "</div><br/>"

        rows.append(row)

    # TODO -- figure out whether to strike out Double and Redouble!!
    return format_html(f"""
    <div class="btn-group">
    {buttonize(bridge.contract.Pass)}{buttonize(bridge.contract.Double)}{buttonize(bridge.contract.Redouble)}
    </div>
    <br/>
    {"\n".join(rows)}
    """)


def card_buttons_as_four_divs(cards: list[bridge.card.Card]) -> SafeString:
    by_suit = {s: [] for s in bridge.card.Suit}
    for c in cards:
        by_suit[c.suit].append(c)

    def card_button(c, color):
        return f"""<button type="button"
        class="btn btn-primary"
        style="--bs-btn-color: {color}; --bs-btn-bg: #ccc">{c}</button>"""

    def single_row_divs(suit, cards):
        color = "red" if suit in {bridge.card.Suit.HEARTS, bridge.card.Suit.DIAMONDS} else "black"
        cols = [card_button(c, color) for c in reversed(cards)]
        return f"""<div class="btn-group">{"".join(cols)}</div><br/>"""

    row_divs = [
        single_row_divs(suit, cards) if cards else "<div>-</div>"
        for suit, cards in sorted(by_suit.items(), reverse=True)
    ]

    return SafeString("<br>" + "\n".join(row_divs))


@logged_in_as_player_required()
def table_detail_view(request, pk):
    table = get_object_or_404(Table, pk=pk)

    # TODO -- figure out if there's a dummy, in which case show those; and figure out if the auction and play are over,
    # in which case show 'em all
    cards_by_direction_display = {}
    for seat, cards in table.cards_by_player().items():
        dem_cards_baby = f"{len(cards)} cards"

        # TODO -- this seems redundant with "show_cards_for"
        if True or seat.player == request.user.player:
            dem_cards_baby = card_buttons_as_four_divs(cards)

        cards_by_direction_display[seat.named_direction] = {
            "player": seat.player,
            "cards": dem_cards_baby,
        }

    context = {
        "bidding_box": _bidding_box(table),
        "card_display": cards_by_direction_display,
        "table": table,
    }

    return TemplateResponse(request, "table_detail.html", context=context)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def new_table_for_two_partnerships(request, pk1, pk2):
    p1 = get_object_or_404(Player, pk=pk1)
    if p1.partner is None:
        return HttpResponseForbidden(f"Hey man {p1=} doesn't have a partner")

    p2 = get_object_or_404(Player, pk=pk2)
    if p2.partner is None:
        return HttpResponseForbidden(f"Hey man {p2=} doesn't have a partner")

    p3 = get_object_or_404(Player, pk=p1.partner.pk)
    p4 = get_object_or_404(Player, pk=p2.partner.pk)

    all_four = {p1, p2, p3, p4}
    if len(all_four) != 4:
        return HttpResponseForbidden(f"Hey man {all_four} isn't four distinct players")

    if request.user.player not in all_four:
        return HttpResponseForbidden(f"Hey man {request.user.player} isn't one of {all_four}")

    t = Table.objects.create_with_two_partnerships(p1, p2)

    return HttpResponseRedirect(reverse("app:table-detail", args=[t.pk]))
    # TODO -- send one of those groovy Server Sent Events
