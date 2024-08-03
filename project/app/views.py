from operator import attrgetter

from django.contrib.auth.mixins import LoginRequiredMixin
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


class ShowSomeHandsDetailView(LoginRequiredMixin, DetailView):
    def get_context_data(self, **kwargs):
        original_context = super().get_context_data(**kwargs)
        return dict(show_cards_for=[self.request.user.username]) | original_context


class PlayerListView(ListView, FormView):
    model = Player
    template_name = "player_list.html"
    submit_button_label = "filter"
    form_class = LookingForLoveForm

    def get_queryset(self):
        filter_val = self.request.GET.get("lookin_for_love")

        qs = self.model.objects.all()
        if filter_val not in (None, "unknown"):
            looking_for_partner = {"Yes": True, "No": False}[filter_val]
            qs = qs.filter(looking_for_partner=looking_for_partner)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[self.submit_button_label] = self.request.GET.get(
            self.submit_button_label,
            None,
        )  # I bet this isn't necessary
        return context


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
