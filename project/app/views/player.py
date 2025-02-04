from __future__ import annotations

import contextlib
import json
import logging
import time
from typing import Any

from django.contrib import messages as django_web_messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods
from django_eventstream import send_event  # type: ignore [import-untyped]

from app.models import Message, PartnerException, Player
from app.models.player import JOIN, SPLIT
from app.models.types import PK

from .misc import AuthedHttpRequest, logged_in_as_player_required

logger = logging.getLogger(__name__)


def player_detail_endpoint(*, player_pk: PK) -> str:
    return reverse("app:player", args=[player_pk])


def partnership_status_channel_name(*, viewer, subject) -> str:
    return f"partnership-status:{viewer.pk=}:{subject.pk=}"


def _splitsville_context(*, request: AuthedHttpRequest, player_pk: PK) -> dict[str, Any]:
    return {
        "button_content": "Splitsville!!",
        "button_submit_value": SPLIT,
        "form_action": player_detail_endpoint(player_pk=player_pk),
        "input_hidden_value": request.get_full_path(),
    }


def _partnerup_context(*, request: AuthedHttpRequest, subject_pk: PK) -> dict[str, Any]:
    return {
        "button_content": "Partner 'em Up, Boss",
        "button_submit_value": JOIN,
        "form_action": player_detail_endpoint(player_pk=subject_pk),
        "input_hidden_value": reverse("app:players")
        + "?has_partner=True&seated=False&exclude_me=True",
    }


def _tableup_context(*, request: AuthedHttpRequest, subject_pk: PK) -> dict[str, Any]:
    assert request.user.player is not None
    return {
        "button_content": "Table Up With Yon Dudes",
        "button_submit_value": "",
        "form_action": reverse(
            "app:new-table", kwargs=dict(pk1=subject_pk, pk2=request.user.player.pk)
        ),
    }


def _find_a_partner_link():
    return format_html(
        """<a style="font-size: 5em;"
              href="{}?has_partner=False&exclude_me=True">Find a partner.</a>""",
        reverse("app:players"),
    )


def _describe_partnership(*, subject: Player, as_viewed_by: Player) -> str:
    if subject.partner is None:
        if subject == as_viewed_by:
            return _find_a_partner_link()

        return f"{subject.name} has no partner 😢"

    possessive_noun = format_html("{}'s", subject.as_link())
    if subject == as_viewed_by:
        possessive_noun = format_html("Your")

    if subject.partner == as_viewed_by:
        text = format_html("{} partner is, gosh, you!", possessive_noun)
    else:
        text = format_html("{} partner is {}", possessive_noun, subject.partner.as_link())

    return format_html("{}", text)


def _get_partner_action_from_context(
    *, request: AuthedHttpRequest, subject: Player, as_viewed_by: Player | None
) -> dict[str, Any] | None:
    """
    If viewer == subject, the outcome is "splitsville" if viewer has a partner; otherwise "Nuttin'".  Otherwise ...

    Each player has (for our purposes) a few possible states:

    * no partner, unseated
    * partner, unseated
    * partner, seated

    Otherwise

    | viewer state      | subject state     | outcome                                                        |
    |-------------------+-------------------+----------------------------------------------------------------|
    | no partner        | no partner        | partnerup                                                      |
    | no partner        | partner, unseated | --                                                             |
    | no partner        | seated            | --                                                             |
    | partner, unseated | no partner        | --                                                             |
    | partner, unseated | partner, unseated | splitsville, if we are each other's partner; otherwise tableup |
    | partner, unseated | seated            | --                                                             |
    | seated            | no partner        | --                                                             |
    | seated            | partner, unseated | --                                                             |
    | seated            | seated            | splitsville, if we are each other's partner; otherwise nothing |
    """

    if as_viewed_by is None:
        return None

    if as_viewed_by == subject:
        if subject.partner is not None:
            return _splitsville_context(request=request, player_pk=subject.pk)

        return None

    if subject.partner == as_viewed_by:
        return _splitsville_context(request=request, player_pk=subject.pk)

    if {subject.partner, as_viewed_by.partner} == {None}:
        return _partnerup_context(request=request, subject_pk=subject.pk)

    if as_viewed_by.partner is None:
        return None

    if {subject.currently_seated, as_viewed_by.currently_seated} == {
        False
    } and not subject.currently_seated:
        if subject.partner == as_viewed_by:
            return _splitsville_context(request=request, player_pk=subject.pk)
        else:
            return _tableup_context(request=request, subject_pk=subject.pk)

    return None


def _partnership_context(
    *, request: AuthedHttpRequest, subject: Player, as_viewed_by: Player
) -> dict[str, Any]:
    context = {
        "as_viewed_by": as_viewed_by,
        "partnership_event_source_endpoint": f"/events/player/{partnership_status_channel_name(viewer=as_viewed_by, subject=subject)}",
        "subject": subject,
        "text": _describe_partnership(subject=subject, as_viewed_by=as_viewed_by),
    }
    if (
        form_stuff := _get_partner_action_from_context(
            request=request, subject=subject, as_viewed_by=as_viewed_by
        )
    ) is not None:
        context["button_context"] = form_stuff

    return context


def _chat_disabled_explanation(*, sender, recipient) -> str | None:
    # You can always mumble to yourself.
    if sender == recipient:
        return None

    if recipient.current_seat:
        return f"{recipient.name} is already seated"
    if sender.current_seat:
        return "You are already seated"

    return None


@require_http_methods(["GET", "POST"])
@logged_in_as_player_required()
def player_detail_view(request: AuthedHttpRequest, pk: PK | None = None) -> HttpResponse:
    assert request.user.player is not None
    who_clicked = request.user.player  # aka "as_viewed_by"
    redirect_to_table = False

    if pk is None:
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])

        pk = request.user.player.pk
        redirect_to_table = True

    subject: Player = get_object_or_404(Player, pk=pk)

    if redirect_to_table and subject.currently_seated:
        assert subject.current_table is not None
        return HttpResponseRedirect(
            reverse("app:hand-detail", kwargs={"pk": subject.current_table.current_hand.pk})
        )

    common_context = {
        "chat_disabled": _chat_disabled_explanation(sender=who_clicked, recipient=subject),
        "chat_event_source_endpoint": f"/events/player/{Message.channel_name_from_players(who_clicked, subject)}",
        "chat_messages": (
            [
                m.as_html()
                for m in Message.objects.get_for_player_pair(who_clicked, subject)
                .order_by("timestamp")
                .all()[0:100]
            ]
        ),
        "chat_post_endpoint": reverse(
            "app:send_player_message",
            kwargs={"recipient_pk": subject.pk},
        ),
        "chat_target": subject,
        "player": subject,
    }

    if request.method == "POST":
        action = request.POST.get("action")

        try:
            if action == SPLIT:
                who_clicked.break_partnership()
            elif action == JOIN:
                who_clicked.partner_with(subject)
            else:
                return HttpResponseBadRequest(
                    escape(f"{action=} but I only accept {SPLIT=} or {JOIN=}")
                )

        except PartnerException as e:
            django_web_messages.add_message(
                request,
                django_web_messages.INFO,
                str(e),
                fail_silently=True,
            )
            return HttpResponseForbidden(str(e))

        if (next_ := request.POST.get("next")) is None:
            next_ = request.get_full_path()

        return HttpResponseRedirect(next_)

    return TemplateResponse(
        request,
        "player_detail.html",
        context=common_context
        | _partnership_context(request=request, subject=subject, as_viewed_by=who_clicked),
    )


@require_http_methods(["POST"])
@logged_in_as_player_required(redirect=False)
def send_player_message(request: AuthedHttpRequest, recipient_pk: PK) -> HttpResponse:
    sender = request.user.player
    recipient: Player = get_object_or_404(Player, pk=recipient_pk)

    if explanation := _chat_disabled_explanation(sender=sender, recipient=recipient):
        return HttpResponseForbidden(explanation)

    channel_name, message_type, message_content = Message.create_player_event_args(
        from_player=sender,
        message=request.POST["message"],
        recipient=recipient,
    )

    send_event(
        channel_name,
        message_type,
        message_content,
        json_encode=False,
    )

    return HttpResponse(
        message_content,
    )


@require_http_methods(["POST"])
@logged_in_as_player_required(redirect=False)
def bot_checkbox_view(request: AuthedHttpRequest, pk: PK) -> HttpResponse:
    playa: Player = get_object_or_404(Player, pk=pk)

    try:
        wait_time = float(request.POST.get("wait_time", "0"))
    except ValueError as e:
        logger.warning("%s; will not wait", e)
        wait_time = 0

    logger.debug(f"Hi folks! {playa.name=} {pk=} {request.POST=}; {wait_time=}")

    if wait_time > 0:
        logger.debug("Waiting %f seconds, since %s", wait_time, request.POST)
        time.sleep(wait_time)

    try:
        playa.toggle_bot()
    except Exception as e:
        return TemplateResponse(
            request,
            "bot-checkbox-partial.html#bot-checkbox-partial",
            context={"error_message": str(e)},
        )

    return TemplateResponse(
        request, "bot-checkbox-partial.html#bot-checkbox-partial", context={"error_message": ""}
    )


def by_name_or_pk_view(request: HttpRequest, name_or_pk: str) -> HttpResponse:
    p = Player.objects.filter(user__username=name_or_pk).first()

    if p is None:
        with contextlib.suppress(ValueError):
            p = Player.objects.filter(pk=name_or_pk).first()

        if p is None:
            logger.debug(f"Nuttin' from pk={name_or_pk=}")
            return HttpResponseNotFound()

    payload = {
        "pk": p.pk,
        "current_table_pk": p.current_table_pk(),
        "current_seat_pk": p.current_seat.pk if p.current_seat is not None else None,
        "name": p.name,
    }

    return HttpResponse(json.dumps(payload), headers={"Content-Type": "text/json"})


def _create_synth_partner_button(request: AuthedHttpRequest) -> str:
    return format_html(
        """<button class="btn btn-primary" type="submit">Gimme synthetic partner, Yo</button>"""
    )


@require_http_methods(["POST"])
@logged_in_as_player_required(redirect=False)
def player_create_synthetic_partner_view(request: AuthedHttpRequest) -> HttpResponse:
    assert request.user.player is not None
    next_ = request.POST["next"]
    try:
        partner = request.user.player.create_synthetic_partner()
    except Exception as e:
        return HttpResponseBadRequest(str(e))

    django_web_messages.add_message(
        request,
        django_web_messages.INFO,
        mark_safe(_describe_partnership(subject=partner, as_viewed_by=request.user.player)),
    )
    return HttpResponseRedirect(next_)


def _create_synth_opponents_button(request) -> str:
    return format_html(
        """<button class="btn btn-primary" type="submit">Gimme synthetic opponents, Yo</button>"""
    )


@require_http_methods(["POST"])
@logged_in_as_player_required(redirect=False)
def player_create_synthetic_opponents_view(request: AuthedHttpRequest) -> HttpResponse:
    assert request.user.player is not None
    next_ = request.POST["next"]
    try:
        request.user.player.create_synthetic_opponents()
    except Exception as e:
        return HttpResponseBadRequest(str(e))
    return HttpResponseRedirect(next_)


def player_list_view(request):
    has_partner = request.GET.get("has_partner")
    seated = request.GET.get("seated")
    exclude_me = request.GET.get("exclude_me")

    qs = Player.objects.all()
    filter_description = []

    player = getattr(request.user, "player", None)

    if player is not None and {"True": True, "False": False}.get(exclude_me) is True:
        qs = qs.exclude(pk=player.pk).exclude(partner=player)
        filter_description.append(f"excluding {player}")

    if (has_partner_filter := {"True": True, "False": False}.get(has_partner)) is not None:
        qs = qs.exclude(partner__isnull=has_partner_filter)
        filter_description.append(("with" if has_partner_filter else "without") + " a partner")

    if (seated_filter := {"True": True, "False": False}.get(seated)) is not None:
        qs = qs.filter(currently_seated=seated_filter)
        filter_description.append("currently seated" if seated_filter else "in the lobby")

    filtered_count = qs.count()
    if player is not None and player.partner is not None:
        qs = qs.annotate(
            maybe_a_link=(
                Q(currently_seated=False)
                & Q(partner__isnull=False)
                & ~Q(pk=player.pk)
                & ~Q(pk=player.partner.pk)
            ),
        )

    total_count = qs.count()
    paginator = Paginator(qs, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Smuggle a button in there.
    for other in page_obj:
        other.action_button = (
            _get_partner_action_from_context(request=request, subject=other, as_viewed_by=player)
            or None
        )

    context = {
        "extra_crap": {"total_count": total_count, "filtered_count": filtered_count},
        "page_obj": page_obj,
        "this_pages_players": json.dumps([p.pk for p in page_obj]),
        "title": ("Players " + ", ".join(filter_description)) if filter_description else "",
    }

    # If viewer has no partner, and there are no other players who lack partners, add a button with which the viewer can
    # create a synthetic player.
    if (
        player is not None
        and player.partner is None
        and has_partner_filter is False
        and filtered_count == 0
    ):
        context["create_synth_partner_button"] = _create_synth_partner_button(request)
        context["create_synth_partner_next"] = (
            reverse("app:players") + "?has_partner=True&seated=False&exclude_me=True"
        )
    # similarly for opponents.
    elif (
        player is not None
        and player.partner is not None
        and has_partner_filter is True
        and seated_filter is False
        and filtered_count < 2
    ):
        context["create_synth_opponents_button"] = _create_synth_opponents_button(request)
        context["create_synth_opponents_next"] = request.get_full_path()

    return render(request, "player_list.html", context)
