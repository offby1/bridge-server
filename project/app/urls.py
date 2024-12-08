from django.urls import path

from .views import home_view, lobby, misc, player, signup_view, table
from .views.board import board_archive_view, board_list_view
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

app_name = "app"

urlpatterns = [
    path("", home_view, name="home"),
    path("basic-auth-login/", misc.basic_auth_login_view, name="basic-auth-login"),
    path("board/", board_list_view, name="board-list"),
    path("board/<pk>/", board_archive_view, name="board-archive"),
    path("call/<hand_pk>/", table.details.call_post_view, name="call-post"),
    path("hand/", hand_list_view, name="hand-list"),
    path("hand/<pk>/", hand_detail_view, name="hand-detail"),
    path(
        "hand/<pk>/updates/<int:calls>/<int:plays>/",
        hand_xscript_updates_view,
        name="hand-xscript-updates",
    ),
    path("serialized/hand/<pk>/", hand_serialized_view, name="serialized-hand-detail"),
    path("hand/<pk>/archive/", hand_archive_view, name="hand-archive"),
    path("hand/<hand_pk>/auction/", auction_partial_view, name="auction-partial"),
    path(
        "hand/<hand_pk>/bidding-box",
        bidding_box_partial_view,
        name="bidding-box-partial",
    ),
    path("hand/<hand_pk>/open-access-toggle", open_access_toggle_view, name="open-access-toggle"),
    path(
        "hand/<table_pk>/four-hands",
        four_hands_partial_view,
        name="four-hands-partial",
    ),
    path("lobby/", lobby.lobby, name="lobby"),
    path("play/<seat_pk>/<hand_pk>/", table.details.play_post_view, name="play-post"),
    path("player/<pk>/", player.player_detail_view, name="player"),
    path("player/<pk>/bot-checkbox-toggle/", player.bot_checkbox_view, name="bot-checkbox-toggle"),
    path("player/<pk>/partnership/", player.partnership_view, name="player_partnership"),
    path("player-by-name/<str:name>/", player.by_name_view, name="player-by-name"),
    path("players/", player.player_list_view, name="players"),
    path("send_lobby_message/", lobby.send_lobby_message, name="send_lobby_message"),
    path(
        "send_player_message/<recipient_pk>",
        player.send_player_message,
        name="send_player_message",
    ),
    path("signup/", signup_view, name="signup"),
    path("table/", table.table_list_view, name="table-list"),
    path("table/<pk>/", table.table_json_view, name="table-json"),
    path(
        "table/<pk>/new-board-plz",
        table.details.new_board_view,
        name="new-board-plz",
    ),
    path("table/<table_pk>/set-table-tempo", set_table_tempo_view, name="set-table-tempo"),
    path("table/new/<pk1>/<pk2>/", table.details.new_table_for_two_partnerships, name="new-table"),
]
