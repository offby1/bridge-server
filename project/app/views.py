from operator import attrgetter

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import render
from django.urls import reverse
from django.views.generic import FormView, ListView
from django.views.generic.detail import DetailView

from .forms import LookingForLoveForm, SignupForm
from .models import Player, Table

# Create your views here.


def home(request):
    return render(request, "home.html")


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


class ShowSomeHandsDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    def get_context_data(self, **kwargs):
        original_context = super().get_context_data(**kwargs)
        return dict(show_cards_for=[self.request.user.username]) | original_context

    def test_func(self):
        player = Player.objects.filter(user__username=self.request.user.username).first()
        # This will show a "403 forbidden" to the admin, since I'm too lazy to think of anything better.
        return player is not None


class PlayerListView(ListView, FormView):
    model = Player
    template_name = "player_list.html"
    submit_button_label = "filter"
    form_class = LookingForLoveForm

    def get_queryset(self):
        qs = self.model.objects.all()
        total_count = qs.count()

        filter_val = self.request.GET.get("lookin_for_love")

        # TODO -- there's gotta be a better way
        if filter_val not in (None, "unknown"):
            looking_for_partner = {
                "Yes": True,
                "true": True,
                "No": False,
                "false": False,
            }[filter_val]
            qs = qs.filter(partner__isnull=looking_for_partner)
        filtered_count = qs.count()
        self.extra_crap = dict(total_count=total_count, filtered_count=filtered_count)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[self.submit_button_label] = self.request.GET.get(
            self.submit_button_label,
            None,
        )
        context["extra_crap"] = self.extra_crap
        return context


# See https://docs.djangoproject.com/en/5.0/topics/auth/default/#django.contrib.auth.mixins.UserPassesTestMixin for an
# alternative
class PlayerDetailView(ShowSomeHandsDetailView):
    model = Player
    template_name = "player_detail.html"

    # TODO -- see if this is really necessary
    def get_context_data(self, **kwargs):
        original_context = super().get_context_data(**kwargs)
        return (
            dict(
                table=self.object.table,
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


# TODO -- investigate https://docs.allauth.org/en/latest/mfa/introduction.html as a better way of signing up and
# authenticating
class SignupView(FormView):
    template_name = "signup.html"
    form_class = SignupForm

    def get_success_url(self):
        return reverse("login")

    def form_valid(self, form):
        form.create_user()
        return super().form_valid(form)
