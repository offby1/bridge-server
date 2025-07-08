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
            board__tournament__play_completion_deadline__gt=django.utils.timezone.now(),
        )
        .order_by("last_action_time")
        .first()
    )


# adapted from https://stackoverflow.com/a/26092256


class LessAnnoyingLogger:
    def __init__(self):
        self._reset()

    def _reset(self):
        self.invocations = 0

    def __getattr__(self, attr):
        self.invocations += 1
        if self.invocations.bit_count() == 1:  # i.e., it's a power of two
            return getattr(logger, attr)
        return lambda *args, **kwargs: None


class Command(BaseCommand):
    def __init__(self, *args, **kwargs):
        self.quiet_logger = LessAnnoyingLogger()
        super().__init__(*args, **kwargs)

    def wait_for_tempo(self, hand_to_play: app.models.Hand) -> None:
        tempo = datetime.timedelta(seconds=hand_to_play.board.tournament.tempo_seconds)
        wait_until = hand_to_play.last_action_time + tempo
        now = django.utils.timezone.now()
        sleepy_time = max(datetime.timedelta(seconds=0), wait_until - now)
        time.sleep(sleepy_time.total_seconds())

    def handle(self, *_args, **_options) -> None:
        while True:
            hand_to_play = get_next_hand()

            if hand_to_play is None:
                self.quiet_logger.info("No playable hand; waiting")
                time.sleep(1)
                continue

            self.quiet_logger.info(
                "\n\n%s", f"Will call or play at {hand_to_play} (pk={hand_to_play.pk})"
            )
            self.wait_for_tempo(hand_to_play)
            xscript: HandTranscript = hand_to_play.get_xscript()

            if (p := hand_to_play.player_who_may_call) is not None:
                self.quiet_logger.info("%s", f"It is {p.name}'s turn to call")
                if p.allow_bot_to_play_for_me:
                    hand_to_play.add_call(call=xscript.auction.random_legal_call())
                    self.quiet_logger._reset()
                else:
                    self.quiet_logger.info("%s", f"{p.name} is human")
                    time.sleep(hand_to_play.board.tournament.tempo_seconds)
            elif (p := hand_to_play.player_who_may_play) is not None:
                self.quiet_logger.info("%s", f"It is {p.name}'s turn to play")
                if p.allow_bot_to_play_for_me or (
                    p == hand_to_play.model_dummy
                    and hand_to_play.model_declarer is not None
                    and hand_to_play.model_declarer.allow_bot_to_play_for_me
                ):
                    hand_to_play.add_play_from_model_player(
                        player=p, card=xscript.slightly_less_dumb_play().card
                    )
                    self.quiet_logger._reset()
                else:
                    self.quiet_logger.info("%s", f"{p.name} is human")
                    time.sleep(hand_to_play.board.tournament.tempo_seconds)
            else:
                raise Exception(
                    "This is confusing -- supposedly this hand is in progress, but nobody can call or play"
                )
