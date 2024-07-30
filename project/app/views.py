from django.shortcuts import render
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from .models import Club, Player, Table

# Create your views here.


def home(request):
    return render(request, "home.html")


def profile(request):
    return render(request, "profile.html")


def club(request):
    # TODO -- either we really are gonna use more than one club, or we aren't; if not, there's no reason to have a Club
    # model.  If so, this is The Wrong Thing.
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
