import logging

from django.db.models import Case, Value, When
from django.template.response import TemplateResponse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
import django.db.models
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_http_methods

from app.views import Forbid
from app.views.misc import AuthedHttpRequest

import app.models
import app.models.tournament

from .misc import logged_in_as_player_required


logger = logging.getLogger(__name__)


def tournament_view(request: AuthedHttpRequest, pk: str) -> TemplateResponse:
    viewer: app.models.Player | None = getattr(request.user, "player", None)

    t: app.models.Tournament = get_object_or_404(app.models.Tournament, pk=pk)
    context = {
        "tournament": t,
        "button": "",
        "comment": "",
        "signed_up_players": app.models.TournamentSignup.objects.filter(tournament=t),
        "speed_things_up_button": "",
    }
    # Only display the movement if every board in the tournament was assigned a group -- otherwise it's an old tournament
    # that didn't have a movement
    if not t.board_set.filter(group__isnull=True).exists():
        try:
            movement = t.get_movement()
        except app.models.tournament.NoPairs:
            pass
        else:
            tab_dict = movement.tabulate_me()
            context["movement_headers"] = tab_dict["headers"]
            context["movement_rows"] = tab_dict["rows"]

    if viewer is not None and viewer.partner is not None and not viewer.currently_seated:
        viewer_signup = app.models.TournamentSignup.objects.filter(player=viewer)
        logger.debug("%s is currently signed up for %s", viewer.name, viewer_signup)

        if not viewer_signup.exists():
            logger.debug("#%s's status is %s", t.display_number, t.status())
            if t.status() is app.models.tournament.OpenForSignup:
                context["button"] = format_html(
                    """<button class="btn btn-primary" type="submit">Sign Me Up, Daddy-O</button>"""
                )
        else:
            relevant_signups = app.models.TournamentSignup.objects.filter(tournament=t)

            non_synths_signed_up_besides_us = (
                relevant_signups.filter(player__synthetic=False)
                .exclude(player__in={viewer, viewer.partner})
                .select_related("player")
            )
            names = [su.player.name for su in non_synths_signed_up_besides_us]
            logger.debug(f"{names=}")
            comment = f"Say, {names=} and none of those are you {viewer.name} or your partner {viewer.partner.name}"
            logger.debug(f"{non_synths_signed_up_besides_us.exists()=}")
            if not non_synths_signed_up_besides_us.exists():
                text_shmext = format_html(
                    """<button class="btn btn-primary" type="submit">Miss Me With This Deadline Shit</button>"""
                )
                comment += text_shmext
                context["speed_things_up_button"] = text_shmext
            context["comment"] = comment

    return TemplateResponse(request=request, template="tournament.html", context=context)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def tournament_signup_view(request: AuthedHttpRequest, pk: str) -> HttpResponse:
    viewer = request.user.player
    assert viewer is not None

    t: app.models.Tournament = get_object_or_404(app.models.Tournament, pk=pk)
    try:
        t.sign_up(viewer)
    except app.models.tournament.TournamentSignupError as e:
        return Forbid(e)
    return HttpResponseRedirect(reverse("app:tournament", kwargs=dict(pk=t.pk)))


def tournament_list_view(request: AuthedHttpRequest) -> TemplateResponse:
    now = timezone.now()

    BROWN = Value("background-color: sandybrown;")
    WHITE = Value("background-color: white;")
    all_ = app.models.Tournament.objects.order_by(
        django.db.models.F("signup_deadline").desc(nulls_last=True)
    ).annotate(
        signup_deadline_style=Case(When(signup_deadline__lt=now, then=BROWN), default=WHITE),
        play_completion_deadline_style=Case(
            When(play_completion_deadline__lt=now, then=BROWN),
            default=WHITE,
        ),
    )

    context = {"tournament_list": all_, "description": "", "button": ""}

    if not app.models.Tournament.objects.open_for_signups().exists():
        context["button"] = format_html(
            """<button class="btn btn-primary" type="submit">Gimme new tournament, Yo</button>"""
        )

    return TemplateResponse(request=request, template="tournament_list.html", context=context)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def new_tournament_view(request: AuthedHttpRequest) -> HttpResponse:
    app.models.Tournament.objects.get_or_create_tournament_open_for_signups()
    return HttpResponseRedirect(reverse("app:tournament-list") + "?open_for_signups=True")


@require_http_methods(["POST"])
@logged_in_as_player_required()
def tournament_void_signup_deadline_view(request: AuthedHttpRequest, pk: str) -> HttpResponse:
    t: app.models.Tournament = get_object_or_404(app.models.Tournament, pk=pk)
    logger.debug(
        "%s",
        f"#{t.display_number} {t.is_complete=} {t.signup_deadline=} {t.signup_deadline_has_passed()=}",
    )
    if not t.is_complete and t.signup_deadline is not None and not t.signup_deadline_has_passed():
        t.signup_deadline = timezone.now()
        t.save()
        app.models.tournament._do_signup_expired_stuff(t)

        logger.debug(
            "%s", f"#{t.display_number} just set signup deadline to 'now': {t.signup_deadline=}"
        )
    return HttpResponseRedirect(reverse("app:tournament", kwargs={"pk": pk}))
