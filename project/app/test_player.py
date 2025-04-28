import datetime
import importlib

from freezegun import freeze_time
from django.conf import settings
from django.contrib import auth

from app.models import Hand, Player, Tournament


def test_player_messages_are_private(usual_setup, everybodys_password) -> None:
    module_name, class_name = settings.EVENTSTREAM_CHANNELMANAGER_CLASS.rsplit(".", maxsplit=1)
    cm = getattr(importlib.import_module(module_name), class_name)()

    north = Player.objects.get_by_name("Jeremy Northam")
    south = Player.objects.get_by_name("J.D. Souther")

    assert cm.can_read_channel(north, north.event_channel_name)
    assert not cm.can_read_channel(north, south.event_channel_name)
    assert cm.can_read_channel(south, south.event_channel_name)
    assert not cm.can_read_channel(south, north.event_channel_name)

    the_hand = Hand.objects.first()
    assert the_hand is not None
    assert north in the_hand.players()
    assert south in the_hand.players()

    assert cm.can_read_channel(north, the_hand.event_channel_name)
    assert cm.can_read_channel(south, the_hand.event_channel_name)

    j_random_user = auth.models.User.objects.create(
        username="J. Random User, Esq", password=everybodys_password
    )

    assert not cm.can_read_channel(j_random_user, the_hand.event_channel_name)


def test_player_timestamp_updates(db, everybodys_password) -> None:
    Today = datetime.datetime.fromisoformat("2020-02-20T20:20:20Z")

    with freeze_time(Today):
        new_guy = Player.objects.create(
            user=auth.models.User.objects.create(username="new guy", password=everybodys_password),
        )

    assert new_guy.created == new_guy.modified == Today

    assert new_guy.last_action() == (Today, "joined")


def test_synth_signup(db) -> None:
    t = Tournament.objects.create()
    bob = Player.objects.create(
        user=auth.models.User.objects.create(username="bob"),
    )
    bob.create_synthetic_partner()

    assert Player.objects.count() == 2

    Player.objects.ensure_six_synths_signed_up(tournament=t)
    assert Player.objects.count() == 8
