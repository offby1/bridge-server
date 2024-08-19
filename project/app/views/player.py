import json

from app.forms import LookingForLoveForm, PartnerForm
from app.models import Message, PartnerException, Player
from django.contrib import messages as django_web_messages
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django_eventstream import send_event

from .misc import logged_in_as_player_required

JOIN = "partnerup"
SPLIT = "splitsville"


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
def partnership_view(request, pk1, pk2):
    one = get_object_or_404(Player, pk=pk1)
    two = get_object_or_404(Player, pk=pk2)

    me = request.user.player

    if me not in (one, two):
        return HttpResponseForbidden(f"Only {one} and {two} may see this page")

    partner = two if me == one else one

    del one
    del two

    if me.partner != partner:
        return HttpResponseForbidden(f"Piss off {me}, {partner} is not your partner!!")

    # Same as player detail for now
    context = {
        "chat_event_source_endpoint": f"/events/player/{Message.channel_name_from_players(me, partner)}",
        "chat_messages": (
            Message.objects.get_for_player_pair(me, partner).order_by("timestamp").all()[0:100]
        ),
        "chat_post_endpoint": reverse(
            "app:send_player_message",
            kwargs={"recipient_pk": partner.pk},
        ),
        "chat_target": partner.name,
        "form": PartnerForm({
            "me": me.id,
            "them": partner.id,
            "action": SPLIT,
        }),
        "me": me,
        "partner": partner,
        "show_cards_for": [me],
    }
    return TemplateResponse(request, "partnership.html", context=context)


@require_http_methods(["GET", "POST"])
@logged_in_as_player_required()
def player_detail_view(request, pk):
    player = get_object_or_404(Player, pk=pk)

    if request.method == "GET":
        if player.partner is not None:
            return HttpResponseRedirect(
                reverse("app:partnership", kwargs=dict(pk1=player.pk, pk2=player.partner.pk)),
            )

    me = request.user.player

    context = {
        "chat_event_source_endpoint": f"/events/player/{Message.channel_name_from_players(me, player)}",
        "chat_messages": (
            Message.objects.get_for_player_pair(me, player).order_by("timestamp").all()[0:100]
        ),
        "chat_post_endpoint": reverse(
            "app:send_player_message",
            kwargs={"recipient_pk": player.pk},
        ),
        "chat_target": player.name,
        "me": me,
        "player": player,
        "show_cards_for": [me],
    }

    if request.method == "GET":
        form = PartnerForm({
            "me": me.pk,
            "them": pk,
            "action": SPLIT if request.user.player.partner is not None else JOIN,
        })
        context["form"] = form
    else:
        form = PartnerForm(request.POST)

        if not form.is_valid():
            return HttpResponse(f"Something's rotten in the state of {form.errors=}")

        them = Player.objects.get(pk=form.cleaned_data.get("them"))
        action = form.cleaned_data.get("action")
        try:
            if action == SPLIT:
                me.break_partnership()
            elif action == JOIN:
                me.partner_with(them)
                return HttpResponseRedirect(
                    reverse("app:partnership", kwargs=dict(pk1=pk, pk2=me.pk)),
                )
        except PartnerException as e:
            django_web_messages.add_message(request, django_web_messages.INFO, str(e))

        return HttpResponseRedirect(reverse("app:player", kwargs=dict(pk=pk)))

    return TemplateResponse(request, "player_detail.html", context=context)


@logged_in_as_player_required(redirect=False)
def send_player_message(request, recipient_pk):
    if request.method == "POST":
        sender = request.user.player
        recipient = get_object_or_404(Player, pk=recipient_pk)

        if sender.is_seated or recipient.is_seated:
            return HttpResponseForbidden(f"Either {sender} or {recipient} is already seated")

        send_event(
            *Message.create_player_event_args(
                from_player=sender,
                message=json.loads(request.body)["message"],
                recipient=recipient,
            ),
        )

    return HttpResponse()
