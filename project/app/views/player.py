import json

from app.forms import LookingForLoveForm, PartnerForm, SeatedForm
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
    lookin_for_love = request.GET.get("lookin_for_love")
    seated = request.GET.get("seated")

    model = Player
    template_name = "player_list.html"

    lfl_form = LookingForLoveForm(request.GET)
    seated_form = SeatedForm(request.GET)

    qs = model.objects.all()
    total_count = qs.count()

    if (lfl_filter := {"True": True, "False": False}.get(lookin_for_love)) is not None:
        qs = qs.filter(partner__isnull=lfl_filter)

    if (seated_filter := {"True": True, "False": False}.get(seated)) is not None:
        qs = qs.filter(seat__isnull=not seated_filter)

    filtered_count = qs.count()
    context = {
        "extra_crap": dict(total_count=total_count, filtered_count=filtered_count),
        "love_form": lfl_form,
        "player_list": qs,
        "seated_form": seated_form,
    }

    return render(request, template_name, context)


@require_http_methods(["GET", "POST"])
@logged_in_as_player_required()
def player_detail_view(request, pk):
    me = request.user.player
    them = get_object_or_404(Player, pk=pk)

    context = {
        "chat_event_source_endpoint": f"/events/player/{Message.channel_name_from_players(me, them)}",
        "chat_messages": (
            Message.objects.get_for_player_pair(me, them).order_by("timestamp").all()[0:100]
        ),
        "chat_post_endpoint": reverse(
            "app:send_player_message",
            kwargs={"recipient_pk": them.pk},
        ),
        "chat_target": them,
        "me": me,
        "player": them,
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
        except PartnerException as e:
            django_web_messages.add_message(request, django_web_messages.INFO, str(e))

        return HttpResponseRedirect(reverse("app:player", kwargs=dict(pk=pk)))

    return TemplateResponse(request, "player_detail.html", context=context)


@logged_in_as_player_required(redirect=False)
def send_player_message(request, recipient_pk):
    if request.method == "POST":
        sender = request.user.player
        recipient = get_object_or_404(Player, pk=recipient_pk)

        if (sender != recipient) and (sender.is_seated or recipient.is_seated):
            return HttpResponseForbidden(f"Either {sender} or {recipient} is already seated")

        send_event(
            *Message.create_player_event_args(
                from_player=sender,
                message=json.loads(request.body)["message"],
                recipient=recipient,
            ),
        )

    return HttpResponse()

    return HttpResponse()
