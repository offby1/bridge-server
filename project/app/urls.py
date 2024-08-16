from django.urls import path

from . import views

app_name = "app"

urlpatterns = [
    path("", views.home, name="home"),
    path("lobby/", views.lobby, name="lobby"),
    path("player/<pk>/", views.player_detail_view, name="player"),
    path("players/", views.player_list_view, name="players"),
    path("send_lobby_message/", views.send_lobby_message, name="send_lobby_message"),
    path(
        "send_player_message/<recipient_pk>", views.send_player_message, name="send_player_message"
    ),
    path("signup/", views.signup_view, name="signup"),
    path("table/", views.table_list_view, name="table"),
    path("table/<pk>", views.table_detail_view, name="table-detail"),
]
