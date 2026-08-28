import logging
from typing import Any, cast

import django.db.models
import django_tables2 as tables
from django.db.models import Case, Value, When
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.views.decorators.http import require_http_methods

import app.models
import app.models.tournament
import app.rendering
from app.utils.movements import Movement, _group_letter
from app.views import Forbid
from app.views.misc import AuthedHttpRequest

from .misc import logged_in_as_player_required

logger = logging.getLogger(__name__)


def annotate_grid_with_hand_links(
    request: AuthedHttpRequest, t: app.models.Tournament, mvmt: Movement
) -> dict[str, Any]:
    tabulate_me = mvmt.tabulate_me()
    annotated_rows = []
    for zb_table, row in enumerate(tabulate_me["rows"]):
        annotated_row = []
        for one_based_round, column in enumerate(row):
            # the first entry here is just the table number.
            if one_based_round == 0:
                annotated_column = column
            else:
                annotated_column = format_html(
                    "<a href='{}'>{}</a>",
                    reverse(
                        "app:hands-by-table-and-board-group",
                        kwargs=dict(
                            tournament_pk=t.pk,
                            table_display_number=zb_table + 1,
                            board_group=_group_letter(one_based_round - 1),
                        ),
                    ),
                    column,
                )

            annotated_row.append(annotated_column)
        annotated_rows.append(annotated_row)
    return {"rows": annotated_rows, "headers": tabulate_me["headers"]}


# The ACBL publishes the laws as one PDF and nothing finer, so the best we can do is
# ask the reader's PDF viewer to open it at the right page.  Page 41 is printed page 17,
# where Law 12C2(a) -- the artificial adjusted score, in the very words below -- begins.
# Chrome and Firefox honour `#page=`; a viewer that doesn't will simply open page one,
# which is a worse answer rather than a broken one.
#
# This file is byte-for-byte the copy in `docs/Laws-of-Duplicate-Bridge.pdf`, so if the
# page ever looks wrong, check that ACBL hasn't quietly replaced it with a new edition:
# `shasum -a 256` the two and see.
LAW_12C2A_URL = "https://web2.acbl.org/documentlibrary/play/Laws-of-Duplicate-Bridge.pdf#page=41"


def _adjusted_score_explanation(t: app.models.Tournament) -> str:
    """Why some of these scores weren't earned at the table, or "" if they all were.

    Worth saying out loud: a pair who barely played can appear in the standings, and a
    pair who played everything can find a board they never got the chance to play sitting
    in their total.  Neither looks like an honest score until you know Law 12 is at work.
    """
    unplayable = t.hands().filter(abandoned_because__isnull=False).count()
    if not unplayable:
        return ""

    return format_html(
        "{} {} in this tournament yielded no result, so nobody could be compared with"
        ' anybody on them.  <a href="{}">Law 12</a> awards an artificial score instead:'
        " 40% to a pair responsible for the board being lost, 60% to a pair who were not,"
        " and 50% each when neither was.  Those awards are part of the totals above.",
        unplayable,
        "board" if unplayable == 1 else "boards",
        LAW_12C2A_URL,
    )


class MatchpointScoreTable(tables.Table):
    _current_viewer: app.models.Player | None = None

    # The rows are pairs, so the two name columns are the halves of one -- "Pair1" and
    # "Pair2", which django-tables2 would otherwise derive from these attribute names,
    # read as though each row held two partnerships.
    pair1 = tables.Column(verbose_name="Player 1")
    pair2 = tables.Column(verbose_name="Player 2")
    matchpoints = tables.Column()
    percentage = tables.Column()

    class Meta:
        row_attrs = {
            "data-pair1-name": lambda record: record.get("pair1_name", ""),
            "data-pair2-name": lambda record: record.get("pair2_name", ""),
            "class": lambda record: _get_row_class(record),
        }

    def __init__(self, *args: Any, viewer: app.models.Player | None = None, **kwargs: Any) -> None:
        # Store viewer as a class variable so the lambda can access it
        MatchpointScoreTable._current_viewer = viewer
        super().__init__(*args, **kwargs)


def _get_row_class(record: dict[str, Any]) -> str:
    """Helper function to determine row class based on viewer."""
    viewer = getattr(MatchpointScoreTable, "_current_viewer", None)
    if viewer is not None:
        pair1_name = record.get("pair1_name")
        pair2_name = record.get("pair2_name")
        viewer_name = viewer.name
        if pair1_name == viewer_name or pair2_name == viewer_name:
            return "viewer-row"
    return ""


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
    if t.signup_deadline_has_passed():
        # Only display the movement if every board in the tournament was assigned a group -- otherwise it's an old
        # tournament that didn't have a movement
        if not t.board_set.filter(group__isnull=True).exists():
            try:
                movement = t.get_movement()
            except app.models.tournament.NoPairs:
                pass
            else:
                context["movement_boards_per_round"] = movement.boards_per_round_per_table
                tab_dict = annotate_grid_with_hand_links(request, t, movement)
                context["movement_headers"] = tab_dict["headers"]
                context["movement_rows"] = tab_dict["rows"]

                if t.is_complete:
                    import math

                    items = t.matchpoints_by_pair().items()
                    l_o_d = []
                    for pair, score in items:
                        player1 = pair[0]  # Player object
                        player2 = pair[1]  # Player object
                        numeric_score = score[1]

                        if math.isnan(numeric_score):
                            string_score = "?"
                        else:
                            string_score = f"{int(round(numeric_score))}%"

                        l_o_d.append(
                            {
                                "pair1": app.rendering.player_link(player1),
                                "pair2": app.rendering.player_link(player2),
                                "pair1_name": player1.name,  # Plain name for comparison
                                "pair2_name": player2.name,  # Plain name for comparison
                                "matchpoints": round(score[0], 1),
                                "percentage": string_score,
                                "_sort_key": -1.0 if math.isnan(numeric_score) else numeric_score,
                            }
                        )

                    # Sort by percentage, not by matchpoints: a pair who missed a board
                    # through no fault of their own play for a smaller total, so their
                    # matchpoints aren't comparable with everyone else's.  A pair with no
                    # percentage at all (nothing to compare against) sorts last.
                    l_o_d.sort(key=lambda x: cast(float, x["_sort_key"]), reverse=True)

                    context["adjusted_score_explanation"] = _adjusted_score_explanation(t)

                    context["matchpoint_score_table"] = MatchpointScoreTable(
                        l_o_d, request=request, viewer=viewer
                    )
        else:
            msg = f"{t} is an old tournament whose boards don't belong to groups; no scores for you"
            logger.info("%s", msg)
            context["missing_matchpoint_explanation"] = msg

    if viewer is not None and viewer.partner is not None and not viewer.currently_seated:
        viewer_signup = app.models.TournamentSignup.objects.filter(player=viewer, tournament=t)
        logger.debug("%s is currently signed up for %s", viewer.name, viewer_signup)

        if not viewer_signup.exists():
            logger.debug("#%s's status is %s", t.display_number, t.status())
            if t.status() is app.models.tournament.OpenForSignup:
                context["button"] = SafeString(
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

            logger.debug(f"{non_synths_signed_up_besides_us.exists()=}")
            if not non_synths_signed_up_besides_us.exists():
                context["speed_things_up_button"] = SafeString(
                    """<button class="btn btn-primary" type="submit">Skip the Deadline</button>"""
                )

    return TemplateResponse(request=request, template="tournament.html", context=context)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def tournament_signup_view(request: AuthedHttpRequest, pk: str) -> HttpResponse:
    viewer = request.user.player
    assert viewer is not None

    t: app.models.Tournament = get_object_or_404(app.models.Tournament, pk=pk)
    try:
        t.sign_up_player_and_partner(viewer)
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
        context["button"] = SafeString(
            """<button class="btn btn-primary" type="submit">Gimme new tournament, Yo</button>"""
        )

    return TemplateResponse(request=request, template="tournament_list.html", context=context)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def new_tournament_view(request: AuthedHttpRequest) -> HttpResponse:
    tournament, _ = app.models.Tournament.objects.get_or_create_tournament_open_for_signups()

    # Sign the creator (and their partner) up, so "I made it, I'm in it" holds
    # without a separate click. Skip quietly if they can't be enrolled -- no
    # partner, already seated, etc.
    creator = request.user.player
    if creator is not None:
        try:
            tournament.sign_up_player_and_partner(creator)
        except app.models.tournament.TournamentSignupError as e:
            logger.debug("Not auto-enrolling %s in %s: %s", creator, tournament, e)

    # Land on the tournament's own page, where the "Sign Me Up" / "Skip the
    # Deadline" buttons are, rather than the list -- otherwise it's easy to miss
    # during the signup window and the clock fills the tournament with bots.
    return HttpResponseRedirect(reverse("app:tournament", kwargs={"pk": tournament.pk}))


@require_http_methods(["POST"])
@logged_in_as_player_required()
def tournament_void_signup_deadline_view(request: AuthedHttpRequest, pk: str) -> HttpResponse:
    t: app.models.Tournament = get_object_or_404(app.models.Tournament, pk=pk)
    logger.debug(
        "%s",
        f"#{t.display_number} {t.is_complete=} {t.signup_deadline=} {t.signup_deadline_has_passed()=}",
    )
    if not t.is_complete and not t.signup_deadline_has_passed():
        app.models.player.Player.objects.ensure_eight_players_signed_up(tournament=t)

        t.signup_deadline = timezone.now()
        t.save()

        app.models.tournament._do_signup_expired_stuff(t)

        logger.debug(
            "%s", f"#{t.display_number} just set signup deadline to 'now': {t.signup_deadline=}"
        )

    # Starting the tournament seated the viewer, so send them straight to their
    # hand -- hand-dispatch picks the interactive vs read-only view for them.
    # Fall back to the tournament page if they somehow aren't seated.
    viewer = request.user.player
    if viewer is not None:
        viewer.refresh_from_db()
        if viewer.current_hand is not None:
            return HttpResponseRedirect(
                reverse("app:hand-dispatch", kwargs={"pk": viewer.current_hand.pk})
            )
    return HttpResponseRedirect(reverse("app:tournament", kwargs={"pk": pk}))
