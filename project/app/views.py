from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.generic import ListView
from django.views.generic.detail import DetailView

from .models import Player, Table

# Create your views here.


def home(request):
    return render(request, "home.html")


@login_required
def profile(request):
    return render(request, "profile.html")


def club(request):
    lobby_players = Player.objects.filter(seat__isnull=True)
    tables = Table.objects.all()
    return render(
        request,
        "club.html",
        context={"lobby": lobby_players, "table_list": tables},
    )


class PlayerDetailView(LoginRequiredMixin, DetailView):
    model = Player
    template_name = "player_detail.html"


class TableListView(ListView):
    model = Table
    template_name = "table_list.html"


class TableDetailView(DetailView):
    model = Table
    template_name = "table_detail.html"
