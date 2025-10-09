from __future__ import annotations

import contextlib
import datetime
import json
import logging
from typing import Any

from django.contrib import messages as django_web_messages
from django.db.models import F, Q
from django.db.models.query import QuerySet
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.templatetags.l10n import localize
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe, SafeString
from django.views.decorators.http import require_http_methods
from django_eventstream import send_event  # type: ignore [import-untyped]
from django_filters import FilterSet  # type: ignore[import-untyped]
from django_filters.views import FilterView  # type: ignore[import-untyped]
import django_tables2 as tables  # type: ignore[import-untyped]

from app.forms import TournamentForm
from app.models import Message, PartnerException, Player
from app.models.player import JOIN, SPLIT
from app.models.types import PK
from app.templatetags.player_extras import sedate_link
from .misc import AuthedHttpRequest, logged_in_as_player_required
from . import Forbid

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
        "input_hidden_value": reverse("app:tournament-list") + "?open_for_signups=True",
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
    Each player has (for our purposes) a few possible states:

    * no partner, unseated
    * partner, unseated
    * partner, seated

    If viewer == subject, the outcome is "splitsville" if viewer has a partner; otherwise nuttin'.  Otherwise ...

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

    if recipient.current_hand_and_direction() is not None:
        return f"{recipient.name} is already seated"
    if sender.current_hand_and_direction() is not None:
        return f"You, {sender.name}, are already seated"

    return None


@require_http_methods(["GET", "POST"])
@logged_in_as_player_required()
def player_detail_view(request: AuthedHttpRequest, pk: PK | None = None) -> HttpResponse:
    assert request.user.player is not None
    who_clicked = request.user.player  # aka "as_viewed_by"
    redirect_to_hand = False

    if pk is None:
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])

        pk = request.user.player.pk
        redirect_to_hand = True

    subject: Player = get_object_or_404(Player, pk=pk)

    if redirect_to_hand and subject.currently_seated:
        current_hand = subject.current_hand
        assert current_hand is not None
        return HttpResponseRedirect(reverse("app:hand-dispatch", kwargs={"pk": current_hand.pk}))

    common_context = {
        "chat_channel_name": Message.channel_name_from_players(who_clicked, subject),
        "chat_disabled": _chat_disabled_explanation(sender=who_clicked, recipient=subject),
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
            return Forbid(e)

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
        return Forbid(explanation)

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


def _bot_checkbox_view_context(request: AuthedHttpRequest, pk: PK) -> dict[str, Any]:
    player: Player = get_object_or_404(Player, pk=pk)

    context = {"error_message": ""}

    try:
        player.toggle_bot()
    except Exception as e:
        context["error_message"] = str(e)
    else:
        assert request.user.player is not None
        request.user.player.refresh_from_db(fields=["allow_bot_to_play_for_me"])

    return context


@require_http_methods(["POST"])
@logged_in_as_player_required(redirect=False)
def bot_checkbox_view(request: AuthedHttpRequest, pk: PK) -> HttpResponse:
    context = _bot_checkbox_view_context(request, pk)
    return TemplateResponse(request, "bot-checkbox.html", context=context)


def by_name_or_pk_view(_request: HttpRequest, name_or_pk: str) -> HttpResponse:
    p = Player.objects.filter(user__username=name_or_pk).first()

    if p is None:
        with contextlib.suppress(ValueError):
            p = Player.objects.filter(pk=name_or_pk).first()

        if p is None:
            logger.debug(f"Nuttin' from pk={name_or_pk=}")
            return HttpResponseNotFound()

    current_hand = p.current_hand

    payload = {
        "pk": p.pk,
        "current_table_number": current_hand.table_display_number
        if current_hand is not None
        else None,
        "current_hand_pk": current_hand.pk if current_hand is not None else None,
        "name": p.name,
    }

    return HttpResponse(json.dumps(payload), headers={"Content-Type": "text/json"})


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


def _row_style(record: Player) -> str:
    def color():
        when = datetime.datetime.min.replace(tzinfo=datetime.UTC)

        if record.last_action is not None:
            when = datetime.datetime.fromisoformat(record.last_action[0])

        now = timezone.now()

        if now - when < datetime.timedelta(seconds=3600):
            return "white"

        if now - when < datetime.timedelta(seconds=3600 * 24):
            return "lightgrey"

        return "darkgrey"

    return format_html(
        "border: 1px dotted; --bs-table-bg: {}",
        color(),
    )


class PlayerTable(tables.Table):
    who = tables.Column(accessor=tables.A("user__username"), verbose_name="Who")
    partner = tables.Column()
    where = tables.Column(empty_values=(), order_by=["current_hand"])
    tournament = tables.Column(
        empty_values=(), order_by=["tournamentsignup"], verbose_name="Tournament"
    )
    last_activity = tables.Column(accessor=tables.A("last_action"), empty_values=())
    action = tables.Column(empty_values=(), orderable=False)

    def order_last_activity(self, queryset, is_descending):
        f_clause = F("last_action")
        if is_descending:
            f_clause = f_clause.desc(nulls_last=True)
        else:
            f_clause = f_clause.asc(nulls_first=True)

        return (queryset.order_by(f_clause), True)

    def render_action(self, record) -> SafeString:
        as_viewed_by = getattr(self.request.user, "player", None)
        if as_viewed_by is None:
            return SafeString("")

        return render_to_string(
            "player_action.html",
            request=self.request,
            context={
                "action_button": _get_partner_action_from_context(
                    request=self.request, subject=record, as_viewed_by=as_viewed_by
                ),
            },
        )

    def render_last_activity(self, value) -> SafeString:
        from django.utils import timezone

        if value is None:
            return SafeString("")

        when = timezone.localtime(datetime.datetime.fromisoformat(value[0]))
        what = value[1]
        return format_html("{} {}: {}", localize(when), when.tzname(), what)

    def render_partner(self, record) -> SafeString:
        return sedate_link(record.partner, self.request.user)

    def render_tournament(self, record) -> SafeString:
        if (ts := getattr(record, "tournamentsignup", None)) is not None:
            t = ts.tournament
            return format_html(
                """ <a href="{}"> {} </a> """,
                reverse("app:tournament", kwargs=dict(pk=t.pk)),
                t,
            )
        elif record.current_hand is not None:
            t = record.current_hand.board.tournament
            return format_html(
                """ <a href="{}"> {} </a> """,
                reverse("app:tournament", kwargs=dict(pk=t.pk)),
                t,
            )
        return SafeString("")

    def render_where(self, record) -> SafeString:
        hand = record.current_hand
        if hand:
            return format_html(
                """ <a href="{}">Table {}</a> """,
                reverse("app:hand-dispatch", kwargs=dict(pk=hand.pk)),
                hand.table_display_number,
            )
        else:
            return format_html("""<a href="{}">lobby</a>""", reverse("app:lobby"))

    def render_who(self, record) -> SafeString:
        return sedate_link(record, self.request.user)

    class Meta:
        row_attrs = {"style": _row_style}


class PlayerFilter(FilterSet):
    class Meta:
        model = Player
        # TODO -- allow filtering on the components of last_action
        exclude = ["last_action", "random_state"]


def _players_for_tournament(tournament_display_number: int) -> Q:
    current_hand = Q(current_hand__board__tournament__display_number=tournament_display_number)
    signup = Q(tournamentsignup__tournament__display_number=tournament_display_number)
    return current_hand | signup


class PlayerListView(tables.SingleTableMixin, FilterView):
    model = Player
    table_class = PlayerTable
    template_name = "player_list.html"

    filterset_class = PlayerFilter
    table_pagination = {"per_page": 15}

    has_partner: bool | None

    def get_queryset(self) -> QuerySet:
        qs = self.model.objects.prepop().order_by(F("last_action").desc(nulls_last=True))

        if (seated := self.request.GET.get("seated")) is not None:
            qs = qs.filter(current_hand__isnull=(seated.lower() != "true"))

        if (hp := self.request.GET.get("has_partner")) is not None:
            self.has_partner = hp.lower() == "true"
            qs = qs.filter(partner__isnull=not self.has_partner)
        else:
            self.has_partner = None

        if (
            tournament_display_number := self.request.GET.get("tournament_display_number")
        ) is not None:
            qs = qs.filter(_players_for_tournament(tournament_display_number))

        if (
            exclude_me := self.request.GET.get("exclude_me")
        ) is not None and self.request.user.player is not None:
            if exclude_me.lower() == "true":
                qs = qs.exclude(pk=self.request.user.player.pk).exclude(
                    partner=self.request.user.player
                )

        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Players"

        if (
            self.request.user is not None
            and getattr(self.request.user, "player", None) is not None
            and self.request.user.player.partner is None
            and not self.has_partner
            and self.get_queryset().count() == 0
        ):
            context["create_synth_partner_button"] = format_html(
                """<button class="btn btn-primary" type="submit">Gimme synthetic partner, Yo</button>"""
            )
            context["create_synth_partner_next"] = (
                reverse("app:tournament-list") + "?open_for_signups=True"
            )

        context["form"] = TournamentForm()
        return context
