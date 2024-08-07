from django.urls import path

from . import views

app_name = "app"

urlpatterns = [
    path("", views.home, name="home"),
    path("lobby/", views.lobby, name="lobby"),
    path("player/<pk>/", views.PlayerDetailView.as_view(), name="player"),
    path("players/", views.player_list_view, name="players"),
    path("signup/", views.SignupView.as_view(), name="signup"),
    path("table/", views.TableListView.as_view(), name="table"),
    path("table/<pk>", views.TableDetailView.as_view(), name="table-detail"),
]
