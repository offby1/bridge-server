from django.shortcuts import render
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
        context={"club": the_only_club, "lobby": lobby_players, "tables": tables},
    )
