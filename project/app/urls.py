from django.urls import path

from .views import home_view, lobby, player, signup_view, table

app_name = "app"

urlpatterns = [
    path("", home_view, name="home"),
    path("call/<table_pk>/", table.details.call_post_view, name="call-post"),
    path("hand/<pk>/archive/", table.hand_archive_view, name="hand-archive"),
    path("lobby/", lobby.lobby, name="lobby"),
    path("play/<seat_pk>/", table.details.play_post_view, name="play-post"),
    path("player/<pk>/", player.player_detail_view, name="player"),
    path("player/<pk>/bot-checkbox-toggle/", player.bot_checkbox_view, name="bot-checkbox-toggle"),
    path("player/<pk>/partnership/", player.partnership_view, name="player_partnership"),
    path("players/", player.player_list_view, name="players"),
    path("send_lobby_message/", lobby.send_lobby_message, name="send_lobby_message"),
    path(
        "send_player_message/<recipient_pk>",
        player.send_player_message,
        name="send_player_message",
    ),
    path("signup/", signup_view, name="signup"),
    path("table/", table.details.table_list_view, name="table"),
    path("table/<pk>/", table.details.table_detail_view, name="table-detail"),
    path("table/<table_pk>/auction/", table.details.auction_partial_view, name="auction-partial"),
    path(
        "table/<table_pk>/bidding-box",
        table.details.bidding_box_partial_view,
        name="bidding-box-partial",
    ),
    path(
        "table/<table_pk>/four-hands",
        table.details.four_hands_partial_view,
        name="four-hands-partial",
    ),
    path(
        "table/<table_pk>/hand-summary-status",
        table.details.hand_summary_view,
        name="hand-summary-view",
    ),
    path(
        "table/<pk>/new-board-plz",
        table.details.new_board_view,
        name="new-board-plz",
    ),
    path("table/new/<pk1>/<pk2>/", table.details.new_table_for_two_partnerships, name="new-table"),
]
