import datetime
import importlib

import time_machine
from django.conf import settings
from django.contrib import auth

from app.models import Hand, Player, Tournament, TournamentSignup
from app.models.playaz import WireCharacterProvider


def test_synthetic_username_falls_back_to_double_barreled_when_pool_exhausted(db: None) -> None:
    # Occupy every single-name slot (prefixed, the way create_synthetic stores
    # them) so the small ~74-name pool is completely full.
    for name in WireCharacterProvider.first_names:
        auth.models.User.objects.create(username="_" + name.lower())

    # This used to raise faker's UniquenessException after 1,000 attempts.
    username = Player.objects._find_unused_username(prefix="_")

    # Instead it falls back to the much larger double-barreled pool, so we never
    # actually run out of names.
    double_barreled = {n.lower() for n in WireCharacterProvider.double_barreled_names}
    assert username[1:] in double_barreled
    assert not auth.models.User.objects.filter(username=username).exists()


def test_create_synths_for_reuses_idle_synthetic_players(db: None) -> None:
    t = Tournament.objects.create()

    # One signed-up pair == odd, so padding with one more pair is needed.
    s1 = Player.objects.create_synthetic()
    s2 = Player.objects.create_synthetic()
    s1.partner_with(s2)
    t.sign_up_player_and_partner(s1)
    assert len(list(t.signed_up_pairs())) == 1

    # Two idle (unpartnered) bots are lying around to be reused.
    idle1 = Player.objects.create_synthetic()
    idle2 = Player.objects.create_synthetic()
    count_before = Player.objects.count()

    TournamentSignup.objects.create_synths_for(t)

    # The idle bots got reused as the padding pair -- no brand-new players minted.
    assert Player.objects.count() == count_before
    assert len(list(t.signed_up_pairs())) == 2
    idle1.refresh_from_db()
    idle2.refresh_from_db()
    assert idle1.partner == idle2


def test_player_messages_are_private(usual_setup: Hand, everybodys_password: str) -> None:
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


def test_player_timestamp_updates(db: None, everybodys_password: str) -> None:
    Today = datetime.datetime.fromisoformat("2020-02-20T20:20:20Z")

    with time_machine.travel(Today, tick=False):
        new_guy = Player.objects.create(
            user=auth.models.User.objects.create(username="new guy", password=everybodys_password),
        )

    assert new_guy.created == new_guy.modified == Today

    assert new_guy.last_action == (Today, "joined")


def test_synth_signup(db: None) -> None:
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

    with time_machine.travel(t.signup_deadline + datetime.timedelta(seconds=1), tick=False):
        mvmt = t.get_movement()
        assert mvmt.num_rounds == 2


def test_bot_is_disabled_at_start_of_hand(usual_setup: Hand) -> None:
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
