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
    calls_by_level = collections.defaultdict(list)

    for call in bridge.contract.Bid.all_exceeding():
        calls_by_level[call.level].append(call)

    mrb = None
    if table.current_handrecord.most_recent_bid is not None:
        mrb = table.current_handrecord.most_recent_bid.libraryCall

    rows = []
    for calls in calls_by_level.values():
        row = '<div class="row">'

        col_divs = []
        for c in calls:
            if mrb is not None and c <= mrb:
                col_divs.append(f'<div class="col"><s>{c}</s></div>')
            else:
                col_divs.append(f'<div class="col">{c}</div>')
        row += "".join(col_divs)

        row += "</div>"

        rows.append(row)

    # TODO -- figure out whether to strike out Double and Redouble!!
    return format_html(f"""
    <div class="bidding-box">


    <div class="row">
    <div class="col">Pass</div><div class="col">Double</div><div class="col">Redouble</div>
    </div>



    {"\n".join(rows)}


    </div>
    """)


def cards_as_four_divs(cards: list[bridge.card.Card]) -> SafeString:
    by_suit = {s: [] for s in bridge.card.Suit}
    for c in cards:
        by_suit[c.suit].append(c)

    def single_row_divs(cards):
        cols = [f"""<div class="col">{c}</div>""" for c in reversed(cards)]
        return f"""

            <div class="row">
            {"".join(cols)}
        </div>

            """

    row_divs = [
        single_row_divs(cards) if cards else "<div>-</div>"
        for suit, cards in sorted(by_suit.items(), reverse=True)
    ]

    return SafeString("\n".join(row_divs))


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
            dem_cards_baby = sorted(cards, reverse=True)

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
