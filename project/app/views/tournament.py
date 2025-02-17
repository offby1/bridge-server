from django.template.response import TemplateResponse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_http_methods

from app.views.misc import AuthedHttpRequest

import app.models

from .misc import logged_in_as_player_required


def tournament_view(request: AuthedHttpRequest, pk: str) -> TemplateResponse:
    t: app.models.Tournament = get_object_or_404(app.models.Tournament, pk=pk)
    return TemplateResponse(request=request, template="tournament.html", context={"tournament": t})


def tournament_list_view(request: AuthedHttpRequest) -> TemplateResponse:
    tournament_list = app.models.Tournament.objects.order_by("pk")
    open_for_signups = request.GET.get("open_for_signups")

    if open_for_signups:
        now = timezone.now()
        tournament_list = tournament_list.filter(
            signup_deadline__gte=now
        )  # .filter(play_completion_deadline__gte=now)

    context = {"tournament_list": tournament_list, "description": "", "button": ""}

    if open_for_signups:
        context["description"] = "Open for signups"
        if not tournament_list.exists():
            context["button"] = format_html(
                """<button class="btn btn-primary" type="submit">Gimme new tournament, Yo</button>"""
            )

    return TemplateResponse(request=request, template="tournament_list.html", context=context)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def new_tournament_view(request: AuthedHttpRequest) -> HttpResponse:
    app.models.Tournament.objects.get_or_create_tournament_open_for_signups()
    return HttpResponseRedirect(reverse("app:tournament-list") + "?open_for_signups=True")
