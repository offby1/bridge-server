from operator import attrgetter

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.urls import reverse
from django.views.generic import FormView, ListView
from django.views.generic.detail import DetailView

from .forms import SignupForm
from .models import Player, Table

# Create your views here.


def home(request):
    return render(request, "home.html")


@login_required
def profile(request):
    return render(request, "profile.html")


# TODO -- use a class-based view
def lobby(request):
    # TODO -- have the db do this for us, somehow
    lobby_players = [p for p in Player.objects.all() if not p.is_seated]

    return render(
        request,
        "lobby.html",
        context={
            "lobby": sorted(lobby_players, key=attrgetter("user.username")),
        },
    )


class ShowSomeHandsDetailView(LoginRequiredMixin, DetailView):
    def get_context_data(self, **kwargs):
        original_context = super().get_context_data(**kwargs)
        return dict(show_cards_for=[self.request.user.username]) | original_context


# See https://docs.djangoproject.com/en/5.0/topics/auth/default/#django.contrib.auth.mixins.UserPassesTestMixin for an
# alternative
class PlayerDetailView(ShowSomeHandsDetailView):
    model = Player
    template_name = "player_detail.html"


class TableListView(ListView):
    model = Table
    template_name = "table_list.html"


class TableDetailView(ShowSomeHandsDetailView):
    model = Table
    template_name = "table_detail.html"


class SignupView(FormView):
    template_name = "signup.html"
    form_class = SignupForm

    def get_success_url(self):
        return reverse("login")

    def form_valid(self, form):
        form.create_user()
        return super().form_valid(form)
