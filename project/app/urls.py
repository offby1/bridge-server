from django.urls import path

from .views import home_view, lobby, player, signup_view, table

app_name = "app"

urlpatterns = [
    path("", home_view, name="home"),
    path("lobby/", lobby.lobby, name="lobby"),
    path("player/<pk>/", player.player_detail_view, name="player"),
    path("player/<pk>/partnership/", player.partnership_view, name="player_partnership"),
    path("players/", player.player_list_view, name="players"),
    path("send_lobby_message/", lobby.send_lobby_message, name="send_lobby_message"),
    path(
        "send_player_message/<recipient_pk>",
        player.send_player_message,
        name="send_player_message",
    ),
    path("signup/", signup_view, name="signup"),
    path("table/", table.table_list_view, name="table"),
    path("table/<pk>", table.table_detail_view, name="table-detail"),
]
