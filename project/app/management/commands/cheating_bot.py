import datetime
import logging
import time

from django.core.management.base import BaseCommand
import django.db.models
import django.utils.timezone

import app.models
from bridge.xscript import HandTranscript


logger = logging.getLogger(__name__)


def get_next_hand() -> app.models.Hand | None:
    expression = django.db.models.Q(pk__in=[])
    for direction in app.models.common.attribute_names:
        expression |= django.db.models.Q(**{f"{direction}__allow_bot_to_play_for_me": True})

    return (
        app.models.Hand.objects.filter(
            expression,
            is_complete=False,
            abandoned_because__isnull=True,
            board__tournament__completed_at__isnull=True,
        )
        .order_by("last_action_time")
        .first()
    )


class Command(BaseCommand):
    def wait_for_tempo(self, hand_to_play: app.models.Hand) -> None:
        tempo = datetime.timedelta(seconds=hand_to_play.board.tournament.tempo_seconds)
        wait_until = hand_to_play.last_action_time + tempo
        now = django.utils.timezone.now()
        sleepy_time = max(datetime.timedelta(seconds=0), wait_until - now)
        logger.debug(
            "%s", f"{tempo=} {hand_to_play.last_action_time=} {wait_until=} {now=} {sleepy_time=}"
        )
        time.sleep(sleepy_time.total_seconds())

    def handle(self, *_args, **_options) -> None:
        while True:
            hand_to_play = get_next_hand()

            if hand_to_play is None:
                logger.info("No playable hand; exiting")
                time.sleep(1)
                exit(0)

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
