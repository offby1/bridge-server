from django.urls import path

from .views import home_view, lobby, player, signup_view, table, three_way_login
from .views.board import (
    board_archive_view,
    board_list_view,
)
from .views.hand import (
    auction_partial_view,
    bidding_box_partial_view,
    four_hands_partial_view,
    hand_archive_view,
    hand_detail_view,
    hand_list_view,
    hand_serialized_view,
    hand_xscript_updates_view,
    open_access_toggle_view,
)
from .views.table import set_table_tempo_view
from .views.tournament import (
    new_tournament_view,
    tournament_list_view,
)

app_name = "app"

urlpatterns = [
    path("", home_view, name="home"),
    path("board/", board_list_view, name="board-list"),
    path("board/<int:pk>/", board_archive_view, name="board-archive"),
    path("call/<hand_pk>/", table.details.call_post_view, name="call-post"),
    path("dev/null/", table.details.dev_null_view, name="dev-null"),
    path("hand/", hand_list_view, name="hand-list"),
    path("hand/<int:pk>/", hand_detail_view, name="hand-detail"),
    path(
        "hand/<int:pk>/updates/<int:calls>/<int:plays>/",
        hand_xscript_updates_view,
        name="hand-xscript-updates",
    ),
    path("serialized/hand/<int:pk>/", hand_serialized_view, name="serialized-hand-detail"),
    path("hand/<int:pk>/archive/", hand_archive_view, name="hand-archive"),
    path("hand/<hand_pk>/auction/", auction_partial_view, name="auction-partial"),
    path(
        "hand/<hand_pk>/bidding-box",
        bidding_box_partial_view,
        name="bidding-box-partial",
    ),
    path("hand/<hand_pk>/open-access-toggle/", open_access_toggle_view, name="open-access-toggle"),
    path(
        "hand/<table_pk>/four-hands",
        four_hands_partial_view,
        name="four-hands-partial",
    ),
    path("lobby/", lobby.lobby, name="lobby"),
    path("play/<hand_pk>/", table.details.play_post_view, name="play-post"),
    path("player/", player.player_detail_view, name="player"),
    path(
        "player/create-synthetic-partner",
        player.player_create_synthetic_partner_view,
        name="player-create-synthetic-partner",
    ),
    path(
        "player/create-synthetic-opponents",
        player.player_create_synthetic_opponents_view,
        name="player-create-synthetic-opponents",
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
    path("send_lobby_message/", lobby.send_lobby_message, name="send_lobby_message"),
    path(
        "send_player_message/<recipient_pk>",
        player.send_player_message,
        name="send_player_message",
    ),
    path("signup/", signup_view, name="signup"),
    path("table/", table.table_list_view, name="table-list"),
    path("table/<int:pk>/", table.table_json_view, name="table-json"),
    path(
        "table/<int:pk>/new-board-plz/",
        table.details.new_board_view,
        name="new-board-plz",
    ),
    path("table/<table_pk>/set-table-tempo/", set_table_tempo_view, name="set-table-tempo"),
    path(
        "table/new/<tournament_pk>/<pk1>/<pk2>/",
        table.details.new_table_for_two_partnerships,
        name="new-table",
    ),
    path("three-way-login/", three_way_login.three_way_login_view, name="three-way-login"),
    path("tournament/", tournament_list_view, name="tournament-list"),
    path("tournament/new/", new_tournament_view, name="new-tournament"),
]
