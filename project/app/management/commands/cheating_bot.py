import datetime
import logging
import time

from django.core.management.base import BaseCommand
import django.utils.timezone

import app.models
from bridge.xscript import HandTranscript


logger = logging.getLogger(__name__)


def get_next_hand() -> tuple[app.models.Hand, datetime.datetime] | None:
    now = django.utils.timezone.now()
    hand_constraints = dict(
        hand__is_complete=False,
        hand__abandoned_because__isnull=True,
        hand__board__tournament__completed_at__isnull=True,
        hand__board__tournament__signup_deadline__lt=now,
    )

    oldest_call = app.models.Call.objects.filter(**hand_constraints).order_by("-modified").first()

    oldest_play = app.models.Play.objects.filter(**hand_constraints).order_by("-modified").first()

    if oldest_call is None and oldest_play is None:
        h = (
            app.models.Hand.objects.filter(
                is_complete=False,
                abandoned_because__isnull=True,
                board__tournament__completed_at__isnull=True,
                board__tournament__signup_deadline__lt=now,
            )
            .order_by("-modified")
            .first()
        )
        if h is None:
            return h
        return (h, h.modified)

    assert oldest_call is not None or oldest_play is not None, f"{oldest_call=} {oldest_play=}"

    if oldest_call is None:
        assert oldest_play is not None, f"{oldest_call=} {oldest_play=}"
        h = oldest_play.hand
        if h is None:
            return h
        return (h, oldest_play.modified)

    assert oldest_call is not None, f"{oldest_call=} {oldest_play=}"

    if oldest_play is None:
        return (oldest_call.hand, oldest_call.modified)

    if oldest_call.modified < oldest_play.modified:
        return (oldest_call.hand, oldest_call.modified)

    return (oldest_play.hand, oldest_play.modified)


class Command(BaseCommand):
    def wait_for_tempo(self, hand_to_play: app.models.Hand) -> None:
        tempo = hand_to_play.board.tournament.tempo_seconds
        last_action_time = hand_to_play.modified.timestamp()
        wait_until = last_action_time + tempo
        now = time.time()
        sleepy_time = max(0, wait_until - now)
        logger.debug("%s", f"{tempo=} {last_action_time=} {wait_until=} {now=} {sleepy_time=}")
        time.sleep(sleepy_time)

    def handle(self, *_args, **_options) -> None:
        while True:
            wat = get_next_hand()

            if wat is None:
                logger.info("No playable hand; sleeping")
                time.sleep(1)
                continue

            hand_to_play: app.models.Hand
            last_action_time: datetime.datetime

            hand_to_play, last_action_time = wat

            logger.info("%s", f"Will call or play at {hand_to_play}")
            self.wait_for_tempo(hand_to_play)
            xscript: HandTranscript = hand_to_play.get_xscript()
            # TODO -- check if player has "let the bot play for me" set!
            if hand_to_play.player_who_may_call is not None:
                libCall = xscript.auction.random_legal_call()

                hand_to_play.add_call(call=libCall)
            elif hand_to_play.player_who_may_play is not None:
                libPlay = xscript.slightly_less_dumb_play()

                hand_to_play.add_play_from_model_player(
                    player=hand_to_play.player_who_may_play, card=libPlay.card
                )
            else:
                raise Exception(
                    "This is confusing -- supposedly this hand is in progress, but nobody can call or play"
                )
