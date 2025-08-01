from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Callable

import bridge.seat
import bridge.xscript
from bridge.auction import Auction
from django.conf import settings
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
)
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models.query import QuerySet
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.views.decorators.http import require_http_methods
from django_filters import FilterSet  # type: ignore[import-untyped]
from django_filters.views import FilterView  # type: ignore[import-untyped]
import django_tables2 as tables  # type: ignore[import-untyped]

import app.models
from app.models.common import attribute_names
from app.models.types import PK
from app.models.utils import assert_type
from app.views import Forbid, NotFound
from app.views.misc import AuthedHttpRequest, logged_in_as_player_required

if TYPE_CHECKING:
    from collections.abc import Iterable

    from bridge.xscript import HandTranscript
    import datetime
    from app.models.hand import AllFourSuitHoldings, Hand


logger = logging.getLogger(__name__)


def _localize(stamp: datetime.datetime, zone_name: str | None = None) -> datetime.datetime:
    if zone_name is not None:
        import zoneinfo

        try:
            zone = zoneinfo.ZoneInfo(zone_name)
            return stamp.astimezone(zone)
        except zoneinfo.ZoneInfoNotFoundError:
            pass

    return stamp


def _seat_div_context(
    *, hand: app.models.Hand, seat: bridge.seat.Seat, viewer_may_control_this_seat: bool
) -> dict[str, Any]:
    ds = hand.display_skeleton(as_dealt=False)
    our_all_four_suit_holding = ds.holdings_by_seat[seat]

    card_html_by_direction = app.views.hand._get_card_html(
        all_four=our_all_four_suit_holding,
        hand=hand,
        viewer_may_control_this_seat=viewer_may_control_this_seat,
    )

    return {
        "active_seat": hand.active_seat_name,
        "cards": card_html_by_direction,
        "id": seat.name,
    }


def _auction_context_for_hand(hand: app.models.Hand) -> dict[str, Any]:
    return {
        "hand": hand,
        "players_starting_with_west": _players_west_first_context_for_hand(hand),
    }


def _players_west_first_context_for_hand(
    hand: app.models.Hand,
) -> Iterable[tuple[str, dict[str, Any]]]:
    context = {}
    p_b_d_list = list(hand.players_by_direction_letter.items())
    # put West first because "Bridge Writing Style Guide by Richard Pavlicek.pdf" says to
    p_b_d_list.insert(0, p_b_d_list.pop(-1))
    # Hightlight whoever's turn it is
    for direction, player in p_b_d_list:
        this_player_context: dict[str, Any] = {"player": player}
        if player == hand.player_who_may_call:
            this_player_context["style"] = """ style="background-color: lightgreen;" """
        else:
            this_player_context["style"] = ""
        context[direction] = this_player_context

    return context.items()


def _bidding_box_context_for_hand(*, hand: Hand, as_viewed_by: app.models.Player) -> dict[str, Any]:
    display_bidding_box = hand.auction.status is bridge.auction.Auction.Incomplete

    disabled = True

    if not as_viewed_by.has_played_hand(hand):
        buttons = "No bidding box 'cuz you are not at this table"
    else:
        allowed_caller = hand.auction.allowed_caller()

        if hand.open_access:
            disabled = False
        else:
            if allowed_caller is not None and (as_viewed_by.name == allowed_caller.name):
                disabled = False

        buttons = bidding_box_buttons(
            auction=hand.auction,
            call_post_endpoint=reverse("app:call-post"),
            disabled_because_out_of_turn=disabled,
        )

    return {
        "bidding_box_buttons": buttons,
        "display_bidding_box": display_bidding_box,
        "disabled": disabled,
    }


def _display_and_control(
    *,
    hand: app.models.Hand,
    seat: bridge.seat.Seat,
    as_viewed_by: app.models.Player | None,
    as_dealt: bool,
) -> dict[str, bool]:
    assert_type(hand, app.models.Hand)
    assert_type(seat, bridge.seat.Seat)
    if as_viewed_by is not None:
        assert_type(as_viewed_by, app.models.Player)
    assert_type(as_dealt, bool)

    board: app.models.Board = hand.board
    seat_is_dummy = hand.dummy and seat == hand.dummy.seat

    wat = board.what_can_they_see(player=as_viewed_by)
    display_cards = (
        as_dealt  # hand is over and we're reviewing it; i.e., the hand is complete
        or hand.open_access
        or wat == board.PlayerVisibility.everything
    )

    current_direction = None
    if as_viewed_by is not None:
        current_direction = as_viewed_by.current_direction(current_hand=hand)
    if current_direction is not None:
        if current_direction == seat.name:
            display_cards |= wat >= board.PlayerVisibility.own_hand
        if seat_is_dummy:
            display_cards |= wat >= board.PlayerVisibility.dummys_hand

    if as_viewed_by is None or not as_viewed_by.currently_seated:
        return {
            "display_cards": bool(display_cards),
            "viewer_may_control_this_seat": False,
        }

    if not display_cards or hand.player_who_may_play is None:
        return {
            "display_cards": display_cards,
            "viewer_may_control_this_seat": False,
        }

    if hand.open_access and not hand.is_complete:
        return {"display_cards": True, "viewer_may_control_this_seat": True}

    return {
        "display_cards": True,
        "viewer_may_control_this_seat": as_viewed_by.controls_seat(
            seat=seat, right_this_second=True
        ),
    }


def _get_card_html(
    *,
    all_four: AllFourSuitHoldings,
    hand: app.models.Hand,
    viewer_may_control_this_seat: bool,
) -> dict[str, list[SafeString]]:
    def _card_to_button(c: bridge.card.Card) -> str:
        return f"""<button
        type="button"
        class="btn btn-primary"
        name="card" value="{c.serialize()}"
        style="--bs-btn-color: {c.color}; --bs-btn-bg: #ccc"
        hx-post="{reverse("app:play-post")}"
        hx-swap="none"
        >{c}</button>"""

    # Meant to look like an active button, but without any hover action.
    def card_text(text: str, *, suit_color: str, opacity: str) -> str:
        return f"""<span
        class="btn btn-primary inactive-button"
        style="--bs-btn-color: {suit_color}; --bs-btn-bg: #ccc; {opacity}"
        >{text}</span>"""

    suits = {}
    for suit, holding in sorted(all_four.items(), reverse=True):
        active = holding.legal_now and viewer_may_control_this_seat

        if holding.cards_of_one_suit:
            opacity = (
                "opacity: 25%;"
                if all_four.this_hands_turn_to_play and not holding.legal_now
                else ""
            )

            suits[suit.name()] = [
                SafeString(
                    _card_to_button(c)
                    if active
                    else card_text(str(c), suit_color=c.color, opacity=opacity)
                )
                for c in sorted(holding.cards_of_one_suit, reverse=True)
            ]
        else:
            # BUGBUG -- this shows e.g. "12 cards" for each of the four suits; we really want to show that message just once
            suits[suit.name()] = [SafeString("—")]  # em dash

    return suits


def _three_by_three_trick_display_context_for_hand(
    hand: app.models.Hand,
    xscript: bridge.xscript.HandTranscript,
) -> dict[str, Any]:
    player_names_by_direction_letter = {
        letter: player.name for letter, player in hand.players_by_direction_letter.items()
    }
    cards_by_direction_letter: dict[str, bridge.card.Card] = {}

    lead_came_from: bridge.seat.Seat | None = None

    winning_direction = None

    if hand.current_trick:
        tt: app.models.hand.TrickTuple
        for index, tt in enumerate(hand.current_trick):
            if index == 0:
                lead_came_from = tt.seat
            cards_by_direction_letter[tt.seat.value] = tt.card
            if tt.winner:
                winning_direction = tt.seat.value
    elif isinstance(xscript.auction.status, bridge.contract.Contract):
        lead_came_from = xscript.next_seat_to_play()

    def c(direction: str) -> str:
        card = cards_by_direction_letter.get(direction)
        color = "black"
        if card is not None:
            color = card.color
        css_classes = []

        if direction == winning_direction:
            css_classes.append("throb-div")

        if card is not None:
            css_classes.append(card.suit.name().lower())

        class_attribute = f'class="{" ".join(css_classes)}"' if css_classes else ""

        player = player_names_by_direction_letter[direction]

        return f"""<div {class_attribute}>{player}<span style="color: {color}">{card or "__"}</span></div>"""

    arrow = ""
    if lead_came_from is not None:
        arrow = {"N": "⬆️", "E": "➡️", "S": "⬇️", "W": "⬅️"}[lead_came_from.value]

    return {
        "three_by_three_trick_display": {
            "rows": [
                ["", c(bridge.seat.Seat.NORTH.value), ""],
                [
                    c(bridge.seat.Seat.WEST.value),
                    f"<span>{arrow}</span>",
                    c(bridge.seat.Seat.EAST.value),
                ],
                ["", c(bridge.seat.Seat.SOUTH.value), ""],
            ],
        },
    }


def _bidding_box_HTML_for_hand_for_player(hand: app.models.Hand, player: app.models.Player) -> str:
    context = _bidding_box_context_for_hand(hand=hand, as_viewed_by=player)
    return render_to_string("bidding-box.html", context)


def _three_by_three_HTML_for_trick(hand: app.models.Hand) -> str:
    xscript = hand.get_xscript()
    context = _three_by_three_trick_display_context_for_hand(hand, xscript)
    return render_to_string("3x3-trick-display.html", context)


def _hand_context_for_player(
    *, hand: app.models.Hand, seat: bridge.seat.Seat, viewer_may_control_this_seat: bool
) -> dict[str, Any]:
    context = _seat_div_context(
        hand=hand, seat=seat, viewer_may_control_this_seat=viewer_may_control_this_seat
    )
    return context | {"class": "hand bigfont"}


def _hand_HTML_for_seat(
    *, hand: app.models.Hand, seat: bridge.seat.Seat, viewer_may_control_this_seat: bool
) -> str:
    context = _hand_context_for_player(
        hand=hand,
        seat=seat,
        viewer_may_control_this_seat=viewer_may_control_this_seat,
    )

    return render_to_string(
        "hand-div.html",
        context,
    )


def auction_history_HTML_for_table(
    *, hand: app.models.Hand, as_viewed_by: app.models.Player | None = None
) -> str:
    context = _auction_context_for_hand(hand) | {"user": as_viewed_by}
    return render_to_string("auction.html", context)


def _annotate_tricks(xscript: HandTranscript) -> Iterable[dict[str, Any]]:
    # Based on "Bridge Writing Style Guide by Richard Pavlicek.pdf" (page 5)
    for t_index, t in enumerate(xscript.tricks):
        plays = []
        winning_seat = "?"

        for p_index, p in enumerate(t.plays):
            if p_index == 0:
                led_suit = p.card.suit
                leading_seat = p.seat

            if p.wins_the_trick:
                winning_seat = p.seat.value

            plays.append(
                {
                    "card": p.card if p_index == 0 or p.card.suit != led_suit else p.card.rank,
                    "wins_the_trick": p.wins_the_trick,
                },
            )

        yield {
            "seat": leading_seat.name[0],
            "number": t_index + 1,
            "plays": plays,
            "ns": winning_seat in "NS",
            "ew": winning_seat in "EW",
        }


def _four_hands_context_for_hand(
    *,
    as_viewed_by: app.models.Player | None = None,
    hand: app.models.Hand,
    xscript: bridge.xscript.HandTranscript | None = None,
    as_dealt: bool = False,
) -> dict[str, Any]:
    skel = hand.display_skeleton(as_dealt=as_dealt)

    cards_by_direction_display = {}
    libSeat: bridge.seat.Seat

    viewers_seat: bridge.seat.Seat | None = None
    for libSeat, suitholdings in skel.items():
        this_seats_player = hand.modPlayer_by_seat(libSeat)

        visibility_and_control = _display_and_control(
            hand=hand,
            seat=libSeat,
            as_viewed_by=as_viewed_by,
            as_dealt=as_dealt,
        )
        if visibility_and_control["display_cards"]:
            card_html_by_suit = _get_card_html(
                all_four=suitholdings,
                hand=hand,
                viewer_may_control_this_seat=visibility_and_control["viewer_may_control_this_seat"],
            )
        else:
            card_html_by_suit = {
                suit.name(): [SafeString(suitholdings.textual_summary)]
                for suit, holding in sorted(suitholdings.items(), reverse=True)
            }

        cards_by_direction_display[libSeat.name] = {
            "cards": card_html_by_suit,
            "player": this_seats_player,
        }

        if as_viewed_by is not None and this_seats_player.pk == as_viewed_by.pk:
            cards_by_direction_display["current_player"] = cards_by_direction_display[libSeat.name]
            assert viewers_seat is None
            viewers_seat = libSeat

    xscript = hand.get_xscript()

    always = _auction_context_for_hand(hand) | {
        "annotated_tricks": list(_annotate_tricks(xscript)),
        "card_display": cards_by_direction_display,
        "dummy_player": (
            hand.get_xscript().auction.dummy if hand.get_xscript().auction.found_contract else None
        ),
        "tournament_status": f"{hand.board.tournament} {hand.board.tournament.is_complete=}",
        "viewers_seat": viewers_seat,
    }

    as_viewed_by_is_dummy = False
    if hand.get_xscript().auction.found_contract and as_viewed_by is not None:
        assert hand.dummy is not None
        as_viewed_by_is_dummy = (
            hand.players_by_direction_letter[hand.dummy.seat.value] == as_viewed_by
        )

    if xscript.auction.found_contract and not as_viewed_by_is_dummy:
        cards_by_direction_display["dummy_hand"] = cards_by_direction_display[
            xscript.auction.dummy.seat.name
        ]

    if not hand.is_complete:
        return always | _three_by_three_trick_display_context_for_hand(hand, xscript=xscript)

    return always


@logged_in_as_player_required()
def auction_partial_view(request: AuthedHttpRequest, hand_pk: PK) -> HttpResponse:
    hand: app.models.Hand = get_object_or_404(app.models.Hand, pk=hand_pk)
    context = _auction_context_for_hand(hand)

    return TemplateResponse(request, "auction-partial.html#auction-partial", context=context)


def bidding_box_buttons(
    *,
    auction: bridge.auction.Auction,
    call_post_endpoint: str,
    disabled_because_out_of_turn=False,
) -> SafeString:
    assert isinstance(auction, bridge.auction.Auction)

    legal_calls = auction.legal_calls()

    def buttonize(*, call: bridge.contract.Call, active=True):
        class_ = "btn btn-primary"
        text = call.str_for_bidding_box()

        if disabled_because_out_of_turn:
            text = text if active else f"<s>{text}</s>"
            active = False
            class_ = "btn btn-danger"

        # All one line for ease of unit testing
        return (
            """<button type="button" """
            + """hx-include="this" """
            + f"""hx-post="{call_post_endpoint}" """
            + """hx-swap="none" """
            + f"""name="call" value="{call.serialize()}" """
            + f"""class="{class_}" {"" if active else "disabled"}>"""
            + text
            + """</button>\n"""
        )

    rows = []
    bids_by_level = [
        [
            bridge.contract.Bid(level=level, denomination=denomination)
            for denomination in [*list(bridge.card.Suit), None]
        ]
        for level in range(1, 8)
    ]

    for bids in bids_by_level:
        row = '<div class="btn-group">'

        buttons = []
        for b in bids:
            active = b in legal_calls
            buttons.append(buttonize(call=b, active=active))

        row += "".join(buttons)

        row += "</div>"

        rows.append(row)

    top_button_group = """<div class="btn-group">"""
    for call in (
        bridge.contract.Pass,
        bridge.contract.Double,
        bridge.contract.Redouble,
    ):
        active = call in legal_calls

        top_button_group += buttonize(call=call, active=active)

    top_button_group += "</div>"

    joined_rows = "\n".join(rows)
    return SafeString(f"""{top_button_group}{joined_rows}""")


def hand_dispatch_view(request: AuthedHttpRequest, pk: PK) -> HttpResponse:
    """
    Returns either a 403 response (with explanatory text), or else the function in this module to call to get the response.
    """
    hand: app.models.Hand = app.models.Hand.objects.get_or_404(pk=pk)

    wat = _error_response_or_viewfunc(hand, request.user)
    if isinstance(wat, HttpResponseForbidden):
        return Custom403(request, wat.text)  # type: ignore[attr-defined]

    if hand.is_abandoned:
        return _everything_read_only_view(request, hand)

    return wat(request, hand)


def _error_response_or_viewfunc(
    hand: app.models.Hand,
    user: AbstractBaseUser | AnonymousUser,
    check_if_will_be_played_again: bool = True,
) -> HttpResponseForbidden | Callable[..., HttpResponse]:
    board = hand.board

    if check_if_will_be_played_again:
        if not board.will_be_played_again():
            return _everything_read_only_view

    player = getattr(user, "player", None)

    if user.is_anonymous or player is None:
        msg = f"Anonymous users like {user} can view only those boards that have been fully played"
        return HttpResponseForbidden(msg)

    match brt := board.relationship_to(player):
        case ("NeverSeenIt", None):
            msg = f"You, {player}, have never seen board (#{board.display_number}), so you cannot see the hand."
            return HttpResponseForbidden(msg)
        case ("CurrentlyPlayingIt", at_hand):
            return (
                _interactive_view
                if hand == at_hand
                else HttpResponseForbidden(
                    f"You, {player}, are currently playing this hand, so you cannot see everybody's cards!"
                )
            )
        case ("AlreadyPlayedIt", at_hand):
            return _everything_read_only_view

    assert False, f"wtf is {brt}"


def _everything_read_only_view(request: AuthedHttpRequest, hand: app.models.Hand) -> HttpResponse:
    xscript = hand.get_xscript()
    a = xscript.auction
    c = a.status

    context = _four_hands_context_for_hand(as_viewed_by=None, hand=hand, as_dealt=True)

    if c is Auction.PassedOut:
        context |= {
            "score": 0,
            "vars_score": {"passed_out": 0},
            "terse_description": _terse_description(hand),
        }
    else:
        broken_down_score = xscript.final_score()

        if broken_down_score == 0:
            score_description = "Passed Out"
        elif broken_down_score is None:
            score_description = "Still being played"
        else:
            score_description = f"{broken_down_score.trick_summary}: "

            if broken_down_score.total < 0:  # defenders got points
                score_description += f"Defenders get {-broken_down_score.total}"
            else:
                score_description += f"Declarer's side get {broken_down_score.total}"

        context |= {
            "active_seat": hand.active_seat_name,
            "history": _players_west_first_context_for_hand(hand),
            "score": score_description,
            "terse_description": _terse_description(hand),
        }

    return TemplateResponse(
        request,
        "read-only_hand.html",
        context=context,
    )


def _interactive_view(request: AuthedHttpRequest, hand: app.models.Hand) -> HttpResponse:
    as_viewed_by = request.user.player

    context = (
        _four_hands_context_for_hand(as_viewed_by=as_viewed_by, hand=hand)
        | {
            "active_seat": hand.active_seat_name,
            "terse_description": _terse_description(hand),
        }
        | _auction_context_for_hand(hand)
    )

    if as_viewed_by is not None:
        context |= _bidding_box_context_for_hand(as_viewed_by=as_viewed_by, hand=hand)

    return TemplateResponse(request, "interactive_hand.html", context=context)


def _terse_description(hand: Hand) -> str:
    return format_html(
        '<a href="{}">{}</a>',
        reverse("app:board-archive", kwargs=dict(pk=hand.board.pk)),
        hand.board,
    )


def Custom403(request: HttpRequest, content: str) -> HttpResponse:
    rv = render(request, "custom403.html", context=dict(content=content))
    rv.status_code = 403
    return rv


def hand_serialized_view(request: AuthedHttpRequest, pk: PK) -> HttpResponse:
    preferred_type = request.get_preferred_type(["text/html", "application/json"])  # type: ignore [attr-defined]

    hand = app.models.Hand.objects.get_or_404(pk=pk)

    # This view is currently only called by bots, and bots only run when a hand is in progress -- that is, they don't review completed hands.
    # So there's no point checking if this board is completed; skipping that check saves a query or two.
    resp = _error_response_or_viewfunc(hand, request.user, check_if_will_be_played_again=False)

    if isinstance(resp, HttpResponseForbidden):
        return Custom403(request, resp.text)  # type: ignore[attr-defined]

    if not request.user.is_authenticated:
        xscript = hand.get_xscript()
    else:
        player = request.user.player
        assert player is not None

        match hand.board.what_can_they_see(player=player):
            case (
                app.models.Board.PlayerVisibility.dummys_hand
                | app.models.Board.PlayerVisibility.own_hand
            ):
                xscript = hand.get_xscript().as_viewed_by(
                    bridge.seat.Seat(player.direction_at_hand(hand)[0])
                )
            case app.models.Board.PlayerVisibility.everything:
                xscript = hand.get_xscript()
            case _:
                return Forbid(
                    "You are not allowed to see neither squat, zip, nada, nor bupkis",
                )

    context = {
        "board": hand.board.display_number,
        "table": hand.table_display_number,
        "tempo_seconds": hand.board.tournament.tempo_seconds,
        "tournament": hand.board.tournament.display_number,
        "xscript": xscript.serializable(),
    }

    if preferred_type == "application/json":
        return HttpResponse(
            json.dumps(context),
            headers={"Content-Type": "application/json"},
        )
    return TemplateResponse(request, "serialized-hand.html", context=context)


class HandFilter(FilterSet):
    class Meta:
        model = app.models.Hand
        fields = ["board__tournament__display_number"]


class HandTable(tables.Table):
    board = tables.Column()
    players = tables.Column(orderable=False)
    result = tables.Column(orderable=False, empty_values=())
    status = tables.Column(accessor=tables.A("status_string"), orderable=False)
    table = tables.Column(accessor=tables.A("table_display_number"), verbose_name="Table")
    tournament_number = tables.Column(
        accessor=tables.A("board__tournament__display_number"), verbose_name="Tournament"
    )

    def render_board(self, value) -> SafeString:
        return format_html(
            """<a href="{}">{}</a>""",
            reverse("app:board-archive", kwargs=dict(pk=value.pk)),
            value.display_number,
        )

    def render_players(self, value) -> SafeString:
        return SafeString(", ".join([p.as_link() for p in value]))

    def render_result(self, record) -> SafeString:
        summary_for_this_viewer, _ = record.summary_as_viewed_by(
            as_viewed_by=getattr(self.request.user, "player", None),
        )
        return format_html(
            """<a href="{}">Hand {}: {}</a>""",
            reverse("app:hand-dispatch", kwargs=dict(pk=record.pk)),
            record.pk,
            summary_for_this_viewer,
        )


class HandListView(tables.SingleTableMixin, FilterView):
    model = app.models.Hand
    table_class = HandTable
    template_name = "hand_list.html"

    filterset_class = HandFilter

    def get_queryset(self) -> QuerySet:
        amended_attr_names = [f"{a}__user" for a in attribute_names]
        played_by = self.request.GET.get("played_by")
        qs = self.model.objects.select_related(
            "board", "board__tournament", *attribute_names, *amended_attr_names
        )
        if played_by is not None:
            qs = qs.filter(app.models.Hand.has_player(played_by))
        return qs


class HandsByTableAndBoardGroupView(HandListView):
    def get_queryset(self) -> QuerySet:
        board_group = self.kwargs.get("board_group")
        table_display_number = self.kwargs.get("table_display_number")
        tournament_pk = self.kwargs.get("tournament_pk")

        qs = super().get_queryset()

        return qs.filter(
            board__group=board_group,
            table_display_number=table_display_number,
            board__tournament=tournament_pk,
        )


@logged_in_as_player_required(redirect=False)
def hand_xscript_updates_view(request, pk: PK, calls: int, plays: PK) -> HttpResponse:
    hand: app.models.Hand = get_object_or_404(app.models.Hand, pk=pk)

    player = request.user.player
    assert player is not None

    if player not in hand.players_by_direction_letter.values():
        return Forbid("You're not at that table")

    whats_new = hand.get_xscript().whats_new(num_calls=calls, num_plays=plays)
    return HttpResponse(json.dumps(whats_new), headers={"Content-Type": "text/json"})


@require_http_methods(["POST"])
@logged_in_as_player_required()
def open_access_toggle_view(request: AuthedHttpRequest, hand_pk: PK) -> HttpResponse:
    if settings.DEPLOYMENT_ENVIRONMENT == "production":
        return NotFound("Geez I dunno what you're talking about")

    hand: app.models.Hand = get_object_or_404(app.models.Hand, pk=hand_pk)

    hand.toggle_open_access()
    return HttpResponse(f"{hand=} {hand.open_access=}")
