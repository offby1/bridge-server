import functools
import json
from operator import attrgetter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse

from .forms import LookingForLoveForm, PartnerForm, SignupForm
from .models import LobbyMessage, PartnerException, Player, Table
from .models import send_lobby_message as slm
from .models import send_player_message as spm
from .models.player import channel_name_from_player_pks


# Set redirect to False for AJAX endoints.
def logged_in_as_player_required(redirect=True):
    def inner_wozzit(view_function):
        @functools.wraps(view_function)
        def non_players_piss_off(request, *args, **kwargs):
            if not redirect:
                if not request.user.is_authenticated:
                    return HttpResponseForbidden("Go away, anonymous scoundrel")

            player = Player.objects.filter(user__username=request.user.username).first()
            if player is None:
                messages.add_message(
                    request,
                    messages.INFO,
                    f"You ({request.user.username}) ain't no player, so you can't see whatever {view_function} would have shown you.",
                )
                return HttpResponseRedirect(reverse("app:players"))

            return view_function(request, *args, **kwargs)

        if redirect:
            return login_required(non_players_piss_off)

        return non_players_piss_off

    return inner_wozzit


def home(request):
    return render(request, "home.html")


def lobby(request):
    # TODO -- have the db do this for us, somehow
    lobby_players = [p for p in Player.objects.all() if not p.is_seated]

    return render(
        request,
        "lobby.html",
        context={
            "lobby": sorted(lobby_players, key=attrgetter("user.username")),
            "lobbymessages": LobbyMessage.objects.order_by("timestamp").all()[0:100],
        },
    )


def player_list_view(request):
    model = Player
    template_name = "player_list.html"
    form_class = LookingForLoveForm

    context = {}

    qs = model.objects.all()
    total_count = qs.count()

    if request.method == "POST":
        form = form_class(request.POST)
        form.full_clean()
        filter_val = form.cleaned_data.get("lookin_for_love")
        filter_val = {"True": True, "False": False}.get(filter_val)

        if filter_val is not None:
            qs = qs.filter(partner__isnull=filter_val)
        filtered_count = qs.count()
        context["extra_crap"] = dict(total_count=total_count, filtered_count=filtered_count)
    else:
        form = form_class()

    context["form"] = form
    context["player_list"] = qs

    return render(request, template_name, context)


@logged_in_as_player_required()
def player_detail_view(request, pk):
    JOIN = "partnerup"
    SPLIT = "splitsville"

    player = get_object_or_404(Player, pk=pk)
    me = Player.objects.get_by_name(request.user.username)
    context = {
        "channel_name": channel_name_from_player_pks(me.pk, player.pl),
        "me": me,
        "player": player,
        "show_cards_for": [request.user.username],
    }

    if request.method == "GET":
        form = PartnerForm({
            "me": request.user.player.id,
            "them": pk,
            "action": SPLIT if request.user.player.partner is not None else JOIN,
        })
        context["form"] = form
    elif request.method == "POST":
        form = PartnerForm(request.POST)

        if not form.is_valid():
            return HttpResponse(f"Something's rotten in the state of {form.errors=}")
        me = Player.objects.get(pk=form.cleaned_data.get("me"))
        them = Player.objects.get(pk=form.cleaned_data.get("them"))
        action = form.cleaned_data.get("action")
        try:
            if action == SPLIT:
                me.break_partnership()
            elif action == JOIN:
                me.partner_with(them)
        except PartnerException as e:
            messages.add_message(request, messages.INFO, str(e))

        return HttpResponseRedirect(reverse("app:player", kwargs=dict(pk=pk)))
    else:
        raise Exception("wtf")

    return TemplateResponse(request, "player_detail.html", context=context)


def table_list_view(request):
    context = {
        "table_list": Table.objects.all(),
    }

    return TemplateResponse(request, "table_list.html", context=context)


@logged_in_as_player_required()
def table_detail_view(request, pk):
    table = get_object_or_404(Table, pk=pk)

    context = {
        "table": table,
        "show_cards_for": [request.user.username],
    }

    return TemplateResponse(request, "table_detail.html", context=context)


# TODO -- investigate https://docs.allauth.org/en/latest/mfa/introduction.html as a better way of signing up and
# authenticating
def signup_view(request):
    def start_over_with_message(message):
        messages.add_message(
            request,
            messages.INFO,
            message,
        )
        context["form"] = SignupForm()
        return TemplateResponse(request, "signup.html", context=context)

    context = {}
    if request.method == "GET":
        context["form"] = SignupForm()
        return TemplateResponse(request, "signup.html", context=context)
    elif request.method == "POST":
        form = SignupForm(request.POST)
        if not form.is_valid():
            # TODO -- isn't there some fancy way to tart up the form with the errors?
            return start_over_with_message(f"Something's rotten in the state of {form.errors=}")

        # TODO: if it's a UNIQUE constraint failure, change the user's password
        try:
            form.create_user()
        except Exception as e:
            return start_over_with_message(str(e))

        return HttpResponseRedirect(reverse("login"))


@logged_in_as_player_required(redirect=False)
def send_lobby_message(request):
    if request.method == "POST":
        print(request.body)
        slm(
            from_player=Player.objects.get_from_user(request.user),
            message=json.loads(request.body)["message"],
        )
    return HttpResponse()


@logged_in_as_player_required(redirect=False)
def send_player_message(request, recipient_pk):
    if request.method == "POST":
        from_player = Player.objects.get_from_user(request.user)
        recipient = get_object_or_404(Player, pk=recipient_pk)

        if from_player.is_seated or recipient.is_seated:
            return HttpResponseForbidden(f"Either {from_player} or {recipient} is already seated")

        spm(
            from_player=from_player,
            message=json.loads(request.body)["message"],
            recipient_pk=recipient.pk,
        )
    return HttpResponse()
