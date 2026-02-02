import datetime
import importlib

from django.conf import settings
from django.contrib import auth
from freezegun import freeze_time

from app.models import Hand, Player, Tournament


def test_player_messages_are_private(usual_setup, everybodys_password) -> None:
    module_name, class_name = settings.EVENTSTREAM_CHANNELMANAGER_CLASS.rsplit(".", maxsplit=1)
    cm = getattr(importlib.import_module(module_name), class_name)()

    north = Player.objects.get_by_name("Jeremy Northam")
    south = Player.objects.get_by_name("J.D. Souther")

    assert cm.can_read_channel(north, north.event_HTML_hand_channel)
    assert not cm.can_read_channel(north, south.event_HTML_hand_channel)
    assert cm.can_read_channel(south, south.event_HTML_hand_channel)
    assert not cm.can_read_channel(south, north.event_HTML_hand_channel)

    the_hand = Hand.objects.first()
    assert the_hand is not None
    assert north in the_hand.players()
    assert south in the_hand.players()

    assert cm.can_read_channel(north, the_hand.event_table_html_channel)
    assert cm.can_read_channel(south, the_hand.event_table_html_channel)

    j_random_user = auth.models.User.objects.create(
        username="J. Random User, Esq", password=everybodys_password
    )

    assert not cm.can_read_channel(j_random_user, the_hand.event_table_html_channel)


def test_player_timestamp_updates(db, everybodys_password) -> None:
    Today = datetime.datetime.fromisoformat("2020-02-20T20:20:20Z")

    with freeze_time(Today):
        new_guy = Player.objects.create(
            user=auth.models.User.objects.create(username="new guy", password=everybodys_password),
        )

    assert new_guy.created == new_guy.modified == Today

    assert new_guy.last_action == (Today, "joined")


def test_synth_signup(db) -> None:
    t = Tournament.objects.create()
    bob = Player.objects.create(
        user=auth.models.User.objects.create(username="bob"),
    )
    bob.create_synthetic_partner()
    t.sign_up_player_and_partner(bob)

    assert Player.objects.count() == 2

    Player.objects.ensure_eight_players_signed_up(tournament=t)
    assert Player.objects.count() == 8

    Player.objects.ensure_eight_players_signed_up(tournament=t)
    assert Player.objects.count() == 8

    with freeze_time(t.signup_deadline + datetime.timedelta(seconds=1)):
        mvmt = t.get_movement()
        assert mvmt.num_rounds == 2


def test_bot_is_disabled_at_start_of_hand(usual_setup) -> None:
    assert Hand.objects.count() == 1
    the_hand = Hand.objects.first()
    assert the_hand is not None
    num_bots = sum(p.allow_bot_to_play_for_me for p in the_hand.players())
    assert num_bots > 0

    for p in the_hand.players():
        p.abandon_my_hand()

    the_hand.refresh_from_db()
    num_bots = sum(p.allow_bot_to_play_for_me for p in the_hand.players())
    assert num_bots == 0
