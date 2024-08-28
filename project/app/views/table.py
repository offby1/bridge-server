import collections

import bridge.contract
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.views.decorators.http import require_http_methods

from ..models import Player, Table
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
    for level, calls in calls_by_level.items():
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

    return format_html(f"""
    <div class="bidding-box">

    <div class="container">
    <div class="row">
    <div class="col">Pass</div><div class="col">Double</div><div class="col">Redouble</div>
    </div>
    </div>

    <div class="container">
    {"\n".join(rows)}
    </div>

    </div>
    """)


def _card_picker(request, pk):
    pass


@logged_in_as_player_required()
def table_detail_view(request, pk):
    table = get_object_or_404(Table, pk=pk)

    # TODO -- figure out if there's a dummy, in which case show those; and figure out if the auction and play are over,
    # in which case show 'em all
    card_display = []
    for seat, cards in table.cards_by_player().items():
        dem_cards_baby = f"{len(cards)} cards"

        if seat.player == request.user.player:
            dem_cards_baby = sorted(cards, reverse=True)

        card_display.append((seat, dem_cards_baby))

    context = {
        "bidding_box": _bidding_box(table),
        "card_display": card_display,
        "card_picker": _card_picker(request, pk),
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

    all_four = set([p1, p2, p3, p4])
    if len(all_four) != 4:
        return HttpResponseForbidden(f"Hey man {all_four} isn't four distinct players")

    if request.user.player not in all_four:
        return HttpResponseForbidden(f"Hey man {request.user.player} isn't one of {all_four}")

    t = Table.objects.create_with_two_partnerships(p1, p2)

    return HttpResponseRedirect(reverse("app:table-detail", args=[t.pk]))
    # TODO -- send one of those groovy Server Sent Events
