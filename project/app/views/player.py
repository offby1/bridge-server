from __future__ import annotations

import contextlib
import json
import logging
import time

from django.contrib import messages as django_web_messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.views.decorators.http import require_http_methods
from django_eventstream import send_event  # type: ignore [import-untyped]

from app.models import Message, PartnerException, Player
from app.models.player import JOIN, SPLIT
from app.models.types import PK

from .misc import AuthedHttpRequest, logged_in_as_player_required

logger = logging.getLogger(__name__)


def player_detail_endpoint(player):
    return reverse("app:player", args=[player.id])


def player_link(player):
    return format_html(
        "<a href='{}'>{}</a>",
        player_detail_endpoint(player),
        player,
    )


def partnership_status_channel_name(*, viewer, subject) -> str:
    return f"partnership-status:{viewer.pk=}:{subject.pk=}"


def _button(*, page_subject, action):
    assert action in (JOIN, SPLIT)
    url = player_detail_endpoint(page_subject)

    return format_html(
        """<button
      hx-post="{}"
      hx-swap="none"
      name="action"
      value={}
      >{}</button>""",
        url,
        action,
        action,
    )


def _find_swinging_singles_link():
    return format_html(
        """<a href="{}?lookin_for_love=True">Find swinging singles in your area.</a>""",
        reverse("app:players"),
    )


def _get_text(subject, as_viewed_by):
    addendum = ""
    if subject.current_seat is None and as_viewed_by.current_seat is None:
        addendum = format_html(
            """ (<a href="{}">other unseated partnerships</a>)""",
            reverse("app:players") + "?seated=False&lookin_for_love=False&exclude_me=True",
        )

    if subject.partner:
        if subject.partner != as_viewed_by:
            text = format_html("{}'s partner is {}", subject, player_link(subject.partner))
        else:
            text = format_html("{}'s partner is, gosh, you!", subject)

        return format_html("{}{}", text, addendum)

    if as_viewed_by == subject:
        return _find_swinging_singles_link()

    return f"{subject} has no partner 😢"


def _get_button(subject, as_viewed_by):
    if subject.partner is None and as_viewed_by.partner is None and subject != as_viewed_by:
        return _button(page_subject=subject, action=JOIN)

    if subject == as_viewed_by and subject.partner is not None:
        return _button(page_subject=subject, action=SPLIT)

    if subject == as_viewed_by.partner:
        return _button(page_subject=subject, action=SPLIT)

    return None


def partnership_context(*, subject, as_viewed_by):
    text = _get_text(subject, as_viewed_by)
    button = _get_button(subject, as_viewed_by)

    return {
        "as_viewed_by": as_viewed_by,
        "button": button,
        "partnership_event_source_endpoint": f"/events/player/{partnership_status_channel_name(viewer=as_viewed_by, subject=subject)}",
        "subject": subject,
        "text": text,
    }


def _chat_disabled_explanation(*, sender, recipient) -> str | None:
    # You can always mumble to yourself.
    if sender == recipient:
        return None

    if recipient.current_seat:
        return f"{recipient} is already seated"
    if sender.current_seat:
        return "You are already seated"

    return None


@require_http_methods(["GET", "POST"])
@logged_in_as_player_required()
def player_detail_view(request: AuthedHttpRequest, pk: PK | None = None) -> HttpResponse:
    assert request.user.player is not None
    who_clicked = request.user.player
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

        except PartnerException as e:
            django_web_messages.add_message(
                request,
                django_web_messages.INFO,
                str(e),
                fail_silently=True,
            )
            return HttpResponseForbidden(str(e))

        return HttpResponse()

    return TemplateResponse(
        request,
        "player_detail.html",
        context=common_context | partnership_context(subject=subject, as_viewed_by=who_clicked),
    )


@require_http_methods(["GET"])
@logged_in_as_player_required()
def partnership_view(request: AuthedHttpRequest, pk: PK) -> HttpResponse:
    subject: Player = get_object_or_404(Player, pk=pk)
    context = partnership_context(subject=subject, as_viewed_by=request.user.player)
    return TemplateResponse(
        request=request,
        template="player_detail.html#partnership-status-partial",
        context=context,
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


def player_list_view(request):
    lookin_for_love = request.GET.get("lookin_for_love")
    seated = request.GET.get("seated")
    exclude_me = request.GET.get("exclude_me")

    qs = Player.objects.all()

    player = getattr(request.user, "player", None)

    if player is not None and {"True": True, "False": False}.get(exclude_me) is True:
        qs = qs.exclude(pk=player.pk).exclude(partner=player)

    if (lfl_filter := {"True": True, "False": False}.get(lookin_for_love)) is not None:
        qs = qs.filter(partner__isnull=lfl_filter)

    if (seated_filter := {"True": True, "False": False}.get(seated)) is not None:
        qs = qs.filter(currently_seated=seated_filter)

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
    paginator = Paginator(qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "extra_crap": {"total_count": total_count, "filtered_count": filtered_count},
        "page_obj": page_obj,
    }

    return render(request, "player_list.html", context)
