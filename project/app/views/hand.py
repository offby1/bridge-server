from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import bridge.seat
import bridge.xscript
from bridge.auction import Auction
from django.conf import settings
from django.core.paginator import Paginator
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.views.decorators.http import require_http_methods
from django_eventstream import get_current_event_id  # type: ignore[import-untyped]

import app.models
from app.models.types import PK
from app.models.utils import assert_type
from app.views import Forbid, NotFound
from app.views.misc import AuthedHttpRequest, logged_in_as_player_required

if TYPE_CHECKING:
    from collections.abc import Iterable

    from bridge.xscript import HandTranscript
    import datetime
    from django.db.models import QuerySet
    from app.models.hand import AllFourSuitHoldings, Hand


logger = logging.getLogger(__name__)


def _auction_context_for_hand(hand) -> dict[str, Any]:
    return {
        "auction_partial_endpoint": reverse("app:auction-partial", args=[hand.pk]),
        "show_auction_history": hand.auction.status is bridge.auction.Auction.Incomplete,
        "hand": hand,
        "history": _auction_history_context_for_hand(hand),
    }


def _auction_history_context_for_hand(hand) -> Iterable[tuple[str, dict[str, Any]]]:
    context = {}
    p_b_d_list = list(hand.players_by_direction_letter.items())
    # put West first because "Bridge Writing Style Guide by Richard Pavlicek.pdf" says to
    p_b_d_list.insert(0, p_b_d_list.pop(-1))
    # Hightlight whoever's turn it is
    for direction, player in p_b_d_list:
        this_player_context = {"player": player}
        if player == hand.player_who_may_call:
            this_player_context["style"] = """ style="background-color: lightgreen;" """
        else:
            this_player_context["style"] = ""
        context[direction] = this_player_context

    return context.items()


def _bidding_box_context_for_hand(request: AuthedHttpRequest, hand: Hand) -> dict[str, Any]:
    as_viewed_by: app.models.Player | None = request.user.player
    assert as_viewed_by is not None

    display_bidding_box = hand.auction.status is bridge.auction.Auction.Incomplete

    if not as_viewed_by.has_played_hand(hand):
        buttons = "No bidding box 'cuz you are not at this table"
    else:
        allowed_caller = hand.auction.allowed_caller()
        disabled = True

        if hand.open_access:
            disabled = False
        else:
            if allowed_caller is not None and (as_viewed_by.name == allowed_caller.name):
                disabled = False

        buttons = bidding_box_buttons(
            auction=hand.auction,
            call_post_endpoint=reverse("app:call-post", args=[hand.pk]),
            disabled_because_out_of_turn=disabled,
        )

    return {
        "bidding_box_buttons": buttons,
        "bidding_box_partial_endpoint": reverse("app:bidding-box-partial", args=[hand.pk]),
        "display_bidding_box": display_bidding_box,
        "show_auction_history": display_bidding_box,
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
        current_direction = as_viewed_by.current_direction()
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

    if seat == getattr(hand.dummy, "seat", None):
        viewer_may_control_this_seat = hand.declarer == as_viewed_by.libraryThing()
    else:
        viewer_may_control_this_seat = hand.player_who_may_play == as_viewed_by

    return {
        "display_cards": True,
        "viewer_may_control_this_seat": viewer_may_control_this_seat,
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
        hx-post="{reverse("app:play-post", kwargs={"hand_pk": hand.pk})}"
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

    # TODO -- use _display_and_control here
    def c(direction: str) -> str:
        card = cards_by_direction_letter.get(direction)
        color = "black"
        if card is not None:
            color = card.color
        css_classes = ["bigfont"]

        if direction == winning_direction:
            css_classes.append("throb-div")

        if card is not None:
            css_classes.append(card.suit.name().lower())

        class_attribute = f'class="{" ".join(css_classes)}"' if css_classes else ""

        return (
            f"""<div {class_attribute}><span style="color: {color}">{card or "__"}</span></div>"""
        )

    arrow = ""
    if lead_came_from is not None:
        arrow = {"N": "⬆️", "E": "➡️", "S": "⬇️", "W": "⬅️"}[lead_came_from.value]

    return {
        "three_by_three_trick_display": {
            "rows": [
                ["&nbsp;", c(bridge.seat.Seat.NORTH.value), "&nbsp;"],
                [
                    c(bridge.seat.Seat.WEST.value),
                    f'<span class="bigfont" style="justify-self: center">{arrow}</span>',
                    c(bridge.seat.Seat.EAST.value),
                ],
                ["&nbsp;", c(bridge.seat.Seat.SOUTH.value), "&nbsp;"],
            ],
        },
    }


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
    request: AuthedHttpRequest,
    hand: app.models.Hand,
    xscript: bridge.xscript.HandTranscript | None = None,
    as_dealt: bool = False,
) -> dict[str, Any]:
    as_viewed_by = None
    if hasattr(request.user, "player"):
        as_viewed_by = request.user.player

    skel = hand.display_skeleton(as_dealt=as_dealt)

    cards_by_direction_display = {}
    libSeat: bridge.seat.Seat

    next_seat_to_play = getattr(hand.get_xscript().next_seat_to_play(), "name", "").lower()

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

    always = {
        "annotated_tricks": list(_annotate_tricks(xscript)),
        "card_display": cards_by_direction_display,
        "dummy_player": (
            hand.get_xscript().auction.dummy if hand.get_xscript().auction.found_contract else None
        ),
        "hand": hand,
        "next_seat_to_play": next_seat_to_play,
        "tournament_status": f"{hand.board.tournament} {hand.board.tournament.is_complete=}",
        "viewers_seat": viewers_seat,
    }

    if xscript.auction.found_contract:
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


@logged_in_as_player_required()
def bidding_box_partial_view(request: AuthedHttpRequest, hand_pk: PK) -> TemplateResponse:
    hand: app.models.Hand = get_object_or_404(app.models.Hand, pk=hand_pk)

    context = _bidding_box_context_for_hand(request, hand) | _auction_context_for_hand(hand)

    return TemplateResponse(
        request,
        "auction.html",
        context=context,
    )


def _maybe_redirect_or_error(
    *,
    hand_is_complete: bool,
    hand_pk: PK,
    player_visibility: app.models.Board.PlayerVisibility,
    request_viewname: str,
) -> HttpResponse | None:
    def redirect_if_different_view(destination_viewname: str) -> HttpResponseRedirect | None:
        if destination_viewname == request_viewname:
            return None
        return HttpResponseRedirect(reverse(destination_viewname, args=[hand_pk]))

    match player_visibility:
        case app.models.Board.PlayerVisibility.nothing:
            return Forbid(
                "You are not allowed to see neither squat, zip, nada, nor bupkis",
            )

        case (
            app.models.Board.PlayerVisibility.dummys_hand
            | app.models.Board.PlayerVisibility.own_hand
        ):
            if (response := redirect_if_different_view("app:hand-detail")) is not None:
                return response

        case app.models.Board.PlayerVisibility.everything:
            if hand_is_complete:
                if (response := redirect_if_different_view("app:hand-archive")) is not None:
                    return response
                return None

            elif (response := redirect_if_different_view("app:hand-detail")) is not None:
                return response
            else:
                logger.debug(
                    f"{player_visibility.name=} for a {hand_is_complete=}; we must have already played this board.  Returning None"
                )
                return None

    return None


def hand_archive_view(request: AuthedHttpRequest, *, pk: PK) -> HttpResponse:
    hand: app.models.Hand = get_object_or_404(app.models.Hand, pk=pk)

    if request.user.is_anonymous and not hand.board.tournament.is_complete:
        return HttpResponseRedirect(settings.LOGIN_URL + f"?next={request.path}")

    player = None if request.user.is_anonymous else request.user.player

    response = _maybe_redirect_or_error(
        hand_is_complete=hand.is_complete,
        hand_pk=hand.pk,
        player_visibility=hand.board.what_can_they_see(player=player),
        request_viewname="app:hand-archive",
    )
    if response is not None:
        return response

    xscript = hand.get_xscript()
    a = xscript.auction
    c = a.status
    if c is Auction.Incomplete:
        return HttpResponseRedirect(reverse("app:hand-detail", args=[hand.pk]))

    if c is Auction.PassedOut:
        context = _four_hands_context_for_hand(request=request, hand=hand, as_dealt=True)
        context |= {
            "score": 0,
            "vars_score": {"passed_out": 0},
            "show_auction_history": False,
            "terse_description": _terse_description(hand),
        }
        return TemplateResponse(
            request,
            "hand_archive.html",
            context=context,
        )

    broken_down_score = xscript.final_score()

    if broken_down_score is None:
        return HttpResponseRedirect(reverse("app:hand-detail", args=[hand.pk]))

    if broken_down_score == 0:
        score_description = "Passed Out"
    else:
        score_description = f"{broken_down_score.trick_summary}: "

        if broken_down_score.total < 0:  # defenders got points
            score_description += f"Defenders get {-broken_down_score.total}"
        else:
            score_description += f"Declarer's side get {broken_down_score.total}"

    context = _four_hands_context_for_hand(request=request, hand=hand, as_dealt=True)
    context |= {
        "score": score_description,
        "show_auction_history": True,
        "history": _auction_history_context_for_hand(hand),
        "terse_description": _terse_description(hand),
    }
    return TemplateResponse(
        request,
        "hand_archive.html",
        context=context,
    )


def _terse_description(hand: Hand) -> str:
    tourney = format_html(
        '<a href="{}?tournament={}">Tournament #{}</a>',
        reverse("app:board-list"),
        hand.board.tournament.pk,
        hand.board.tournament.display_number,
    )

    table = format_html(
        "Table #{}",
        hand.table_display_number,
    )

    board = format_html(
        '<a href="{}">Board #{} ({})</a>',
        reverse("app:board-archive", kwargs=dict(pk=hand.board.pk)),
        hand.board.display_number,
        hand.board.vulnerability_string(),
    )

    return SafeString(" ".join([tourney, table, board]))


def hand_detail_view(request: AuthedHttpRequest, pk: PK) -> HttpResponse:
    hand: app.models.Hand = get_object_or_404(app.models.Hand, pk=pk)

    # TODO -- don't require that the entire tournament be complete; instead, require only that this particular board
    # will not be played again.
    if request.user.is_anonymous and not hand.board.tournament.is_complete:
        return HttpResponseRedirect(settings.LOGIN_URL + f"?next={request.path}")

    player = getattr(request.user, "player", None)

    # TODO -- we used to forbid viewing of hands sometimes; it's not clear if we should still do that, and if so,
    # exactly when
    # e.g.
    # If player is not seated at this table, only let them see the hand if they've already completed playing the board.

    response = _maybe_redirect_or_error(
        hand_pk=hand.pk,
        hand_is_complete=hand.is_complete,
        player_visibility=hand.board.what_can_they_see(player=player),
        request_viewname="app:hand-detail",
    )

    if response is not None:
        return response

    context = (
        _four_hands_context_for_hand(request=request, hand=hand)
        | {"terse_description": _terse_description(hand)}
        | _auction_context_for_hand(hand)
        | _bidding_box_context_for_hand(request, hand)
    )

    if (
        player is not None
        and (other_hand := player.hand_at_which_we_played_board(hand.board)) is not None
    ):
        context["hand_at_which_I_played_this_board"] = {
            "description": str(other_hand),
            "link": reverse("app:hand-detail", args=[other_hand.pk]),
        }

    return TemplateResponse(request, "hand_detail.html", context=context)


def hand_xperimental_view(request: AuthedHttpRequest, pk: PK) -> HttpResponse:
    def _localize(stamp: datetime.datetime) -> datetime.datetime:
        if (zone_name := request.session.get("detected_tz")) is not None:
            import zoneinfo

            try:
                zone = zoneinfo.ZoneInfo(zone_name)
                return stamp.astimezone(zone)
            except zoneinfo.ZoneInfoNotFoundError:
                pass
        logger.warning(f"'detected_tz' is {zone_name}; returning timestamp unchanged")
        return stamp

    hand: app.models.Hand = get_object_or_404(app.models.Hand, pk=pk)
    # TODO -- don't require that the entire tournament be complete; instead, require only that this particular board
    # will not be played again.

    if request.user.is_anonymous and not hand.board.tournament.is_complete:
        return HttpResponseForbidden(
            f"This tournament (#{hand.board.tournament.display_number}) won't yet complete"
            f" until {_localize(hand.board.tournament.play_completion_deadline)}, so you can't see this hand now."
        )

    context = (
        _four_hands_context_for_hand(request=request, hand=hand)
        | {"terse_description": _terse_description(hand)}
        | _auction_context_for_hand(hand)
        | _bidding_box_context_for_hand(request, hand)
    )

    return TemplateResponse(request, "hand_xpermiment.html", context=context)


def hand_serialized_view(request: AuthedHttpRequest, pk: PK) -> HttpResponse:
    hand: app.models.Hand = get_object_or_404(app.models.Hand, pk=pk)

    if request.user.is_anonymous and not hand.board.tournament.is_complete:
        return Forbid("You are anonymous, and this tournament isn't complete")

    if request.user.is_anonymous:
        xscript = hand.get_xscript()
    else:
        player = request.user.player
        assert player is not None

        match hand.board.what_can_they_see(player=player):
            case (
                app.models.Board.PlayerVisibility.dummys_hand
                | app.models.Board.PlayerVisibility.own_hand
            ):
                xscript = hand.get_xscript().as_viewed_by(player.libraryThing())
            case app.models.Board.PlayerVisibility.everything:
                xscript = hand.get_xscript()
            case _:
                return Forbid(
                    "You are not allowed to see neither squat, zip, nada, nor bupkis",
                )

    return HttpResponse(
        json.dumps(
            {
                "board": hand.board.display_number,
                "current_event_ids_by_player_name": {
                    p.name: get_current_event_id([p.event_channel_name])
                    for _, p in hand.players_by_direction_letter.items()
                },
                "table": hand.table_display_number,
                "tournament": hand.board.tournament.display_number,
                "xscript": xscript.serializable(),
            }
        ),
        headers={"Content-Type": "text/json"},
    )


def hand_list_view(request: HttpRequest) -> HttpResponse:
    hand_pks = request.GET.get("hand_pks")
    player_pk = request.GET.get("played_by")

    player: app.models.Player | None = None
    hand_list: QuerySet[Hand]
    if hand_pks is not None:
        hand_list = app.models.Hand.objects.filter(pk__in=hand_pks.split(","))
    else:
        hand_list = app.models.Hand.objects.order_by(
            "board__tournament__display_number", "board__display_number", "id"
        )

    if player_pk is not None:
        player = get_object_or_404(app.models.Player, pk=player_pk)
        hand_list = player.hands_played.all()

    paginator = Paginator(hand_list, 16)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    h: Hand
    for h in page_obj.object_list:
        h.summary_for_this_viewer, h.score_for_this_viewer = h.summary_as_viewed_by(
            as_viewed_by=getattr(request.user, "player", None),
        )
    context = {
        "filtered_count": paginator.count,
        "page_obj": page_obj,
        "played_by": "" if player is None else f"played_by={player.pk}",
        "player": player,
    }

    return render(request, "hand_list.html", context=context)


def hands_by_table_and_board_group(
    request: AuthedHttpRequest, tournament_pk: PK, table_display_number: int, board_group: str
) -> HttpResponse:
    player: app.models.Player | None = None if request.user.is_anonymous else request.user.player

    filter_kwargs = dict(
        board__group=board_group,
        table_display_number=table_display_number,
        board__tournament=tournament_pk,
    )

    qs = app.models.Hand.objects.filter(**filter_kwargs)
    logger.debug("%s => %s", filter_kwargs, qs)

    hands = []
    for h in qs:
        h.summary_for_this_viewer, _ = h.summary_as_viewed_by(as_viewed_by=player)
        hands.append(h)

    paginator = Paginator(hands, 16)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "filtered_count": paginator.count,
        "page_obj": page_obj,
        "player": None,
    }

    return render(request, "hand_list.html", context=context)


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
