import logging

from django.template.response import TemplateResponse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_http_methods

from app.views.misc import AuthedHttpRequest

import app.models
import app.models.tournament

from .misc import logged_in_as_player_required


logger = logging.getLogger(__name__)


def tournament_view(request: AuthedHttpRequest, pk: str) -> TemplateResponse:
    viewer = request.user.player

    t: app.models.Tournament = get_object_or_404(app.models.Tournament, pk=pk)
    context = {"tournament": t, "button": ""}
    # TODO -- if our caller is not signed up for any tournaments, *and* if this tournament is open for signups, display a big "sign me up" button.
    current_signups = app.models.TournamentSignups.objects.filter(player=viewer)
    logger.debug("%s is currently signed up for %s", viewer.name, current_signups)

    if not current_signups.exists():
        logger.debug("%s's status is %s", t.display_number, t.status())
        if t.status() is app.models.tournament.OpenForSignup:
            context["button"] = (
                f"Oh! I guess I should let {viewer.name} sign up for {t.display_number}."
            )
    return TemplateResponse(request=request, template="tournament.html", context=context)


def tournament_list_view(request: AuthedHttpRequest) -> TemplateResponse:
    all_ = app.models.Tournament.objects.order_by("pk")

    now = timezone.now()

    open_ = all_.filter(signup_deadline__gte=now).filter(play_completion_deadline__gte=now)

    context = {"tournament_list": all_, "description": "", "button": ""}

    if not open_.exists():
        context["button"] = format_html(
            """<button class="btn btn-primary" type="submit">Gimme new tournament, Yo</button>"""
        )

    return TemplateResponse(request=request, template="tournament_list.html", context=context)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def new_tournament_view(request: AuthedHttpRequest) -> HttpResponse:
    app.models.Tournament.objects.get_or_create_tournament_open_for_signups()
    return HttpResponseRedirect(reverse("app:tournament-list") + "?open_for_signups=True")
