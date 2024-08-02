from operator import attrgetter

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


# TODO -- use a class-based view
def lobby(request):
    # TODO -- have the db do this for us, somehow

    # TODO -- partition the lobby into two lists: players who are looking for partners, and players who aren't.
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

    # Ensure that if we're not invoked with the pk of some user, we fall back to the currently-logged-in user.
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        pk = self.kwargs.get(self.pk_url_kwarg)

        if pk is None:
            user = self.request.user
            if user.is_anonymous:
                # This is dumb, but since this view has LoginRequiredMixin, we won't actually display this.
                self.kwargs[self.pk_url_kwarg] = self.model.objects.first().id
            else:
                self.kwargs[self.pk_url_kwarg] = self.model.objects.get(user=user).id

    def get_context_data(self, **kwargs):
        original_context = super().get_context_data(**kwargs)
        return (
            dict(
                my_table=self.object.my_table,
                looking_for_partner=self.object.looking_for_partner,
            )
            | original_context
        )


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
