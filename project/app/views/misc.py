import functools

from django.contrib import messages as django_web_messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse

from ..models import Player


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
                django_web_messages.add_message(
                    request,
                    django_web_messages.INFO,
                    f"You ({request.user.username}) ain't no player, so you can't see whatever {view_function} would have shown you.",
                )
                return HttpResponseRedirect(reverse("app:home"))

            return view_function(request, *args, **kwargs)

        if redirect:
            return login_required(non_players_piss_off)

        return non_players_piss_off

    return inner_wozzit
