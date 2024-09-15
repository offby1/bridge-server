from django.conf import settings
from django.urls import path

from .views import home_view, lobby, player, signup_view, table

app_name = "app"

urlpatterns = [
    path("", home_view, name="home"),
    path("call/<table_pk>/", table.call_post_view, name="call-post"),
    path("play/<seat_pk>/", table.play_post_view, name="play-post"),
    path("lobby/", lobby.lobby, name="lobby"),
    path("player/<pk>/", player.player_detail_view, name="player"),
    path("player/<pk>/bot-checkbox-toggle", player.bot_checkbox_view, name="bot-checkbox-toggle"),
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
    path("table/<table_pk>/auction", table.auction_partial_view, name="auction-partial"),
    path(
        "table/<table_pk>/bidding-box",
        table.bidding_box_partial_view,
        name="bidding-box-partial",
    ),
    path(
        "table/<table_pk>/four-hands",
        table.four_hands_partial_view,
        name="four-hands-partial",
    ),
    path(
        "table/<table_pk>/handrecord-summary-status",
        table.handrecord_summary_view,
        name="handrecord-summary-view",
    ),
    path("table/new/<pk1>/<pk2>", table.new_table_for_two_partnerships, name="new-table"),
]

if settings.POKEY_BOT_BUTTONS:
    urlpatterns.append(
        path("yo/bot/", table.poke_de_bot, name="poke-de-bot"),
    )
