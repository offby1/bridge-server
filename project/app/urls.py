from django.urls import path

from .views import home_view, lobby, player, signup_view, table, three_way_login
from .views.board import (
    board_archive_view,
    board_list_view,
)
from .views.hand import (
    auction_partial_view,
    hand_dispatch_view,
    HandListView,
    HandsByTableAndBoardGroupView,
    hand_serialized_view,
    hand_xscript_updates_view,
    open_access_toggle_view,
)

from .views.tournament import (
    new_tournament_view,
    tournament_list_view,
    tournament_signup_view,
    tournament_view,
    tournament_void_signup_deadline_view,
)

app_name = "app"

urlpatterns = [
    path("", home_view, name="home"),
    path("board/", board_list_view, name="board-list"),
    path("board/<int:pk>/", board_archive_view, name="board-archive"),
    path("call/", table.details.call_post_view, name="call-post"),
    path("hand/", HandListView.as_view(), name="hand-list"),
    path(
        "hand/<int:tournament_pk>/<int:table_display_number>/<str:board_group>/",
        HandsByTableAndBoardGroupView.as_view(),
        name="hands-by-table-and-board-group",
    ),
    path("hand/<int:pk>/", hand_dispatch_view, name="hand-dispatch"),
    path(
        "hand/<int:pk>/updates/<int:calls>/<int:plays>/",
        hand_xscript_updates_view,
        name="hand-xscript-updates",
    ),
    path("serialized/hand/<int:pk>/", hand_serialized_view, name="serialized-hand-detail"),
    path("hand/<hand_pk>/auction/", auction_partial_view, name="auction-partial"),
    path("hand/<hand_pk>/open-access-toggle/", open_access_toggle_view, name="open-access-toggle"),
    path("lobby/", lobby.lobby, name="lobby"),
    path("play/", table.details.play_post_view, name="play-post"),
    path("table/", table.details.sekrit_test_forms_view, name="sekrit-test-forms"),
    path("player/", player.player_detail_view, name="player"),
    path(
        "player/create-synthetic-partner",
        player.player_create_synthetic_partner_view,
        name="player-create-synthetic-partner",
    ),
    path("player/<int:pk>/", player.player_detail_view, name="player"),
    path(
        "player/<int:pk>/bot-checkbox-toggle/", player.bot_checkbox_view, name="bot-checkbox-toggle"
    ),
    path(
        "player-by-name-or-pk/<str:name_or_pk>/",
        player.by_name_or_pk_view,
        name="player-by-name-or-pk",
    ),
    path("players/", player.player_list_view, name="players"),
    path("new-players/", player.PlayerListView.as_view(), name="new-players"),
    path("send_lobby_message/", lobby.send_lobby_message, name="send_lobby_message"),
    path(
        "send_player_message/<recipient_pk>",
        player.send_player_message,
        name="send_player_message",
    ),
    path("signup/", signup_view, name="signup"),
    path("three-way-login/", three_way_login.three_way_login_view, name="three-way-login"),
    path("tournament/", tournament_list_view, name="tournament-list"),
    path("tournament/<int:pk>/", tournament_view, name="tournament"),
    path("tournament/signup/<int:pk>/", tournament_signup_view, name="tournament-signup"),
    path("tournament/new/", new_tournament_view, name="new-tournament"),
    path(
        "tournament/void-signup-deadline/<int:pk>",
        tournament_void_signup_deadline_view,
        name="tournament-void-signup-deadline",
    ),
]
