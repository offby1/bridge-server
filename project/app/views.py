from django.shortcuts import render
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from .models import Club, Player, Table

# Create your views here.


def duh(request):
    return render(request, "welcome.html")


def profile(request):
    return render(request, "profile.html")


def club(request):
    the_only_club = Club.objects.first()
    lobby_players = Player.objects.filter(table__isnull=True)
    tables = Table.objects.filter(club=the_only_club)
    return render(
        request,
        "club.html",
        context={"club": the_only_club, "lobby": lobby_players, "table_list": tables},
    )


class PlayerDetailView(DetailView):
    model = Player


class TableListView(ListView):
    model = Table
    template_name = "table_list.html"
