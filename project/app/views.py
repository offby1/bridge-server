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


def player_list_view(request):
    model = Player
    template_name = "player_list.html"
    form_class = LookingForLoveForm

    context = {}

    qs = model.objects.all()
    total_count = qs.count()

    if request.method == "POST":
        form = form_class(request.POST)
        form.full_clean()
        filter_val = form.cleaned_data.get("lookin_for_love")
        filter_val = {"True": True, "False": False}.get(filter_val)

        if filter_val is not None:
            qs = qs.filter(partner__isnull=filter_val)
        filtered_count = qs.count()
        context["extra_crap"] = dict(total_count=total_count, filtered_count=filtered_count)
    else:
        form = form_class()

    context["form"] = form
    context["player_list"] = qs

    return render(request, template_name, context)


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
