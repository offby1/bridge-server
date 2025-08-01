import datetime
import logging
import time

from django.core.management.base import BaseCommand
import django.db.models
import django.utils.timezone

import app.models
from bridge.xscript import HandTranscript


logger = logging.getLogger(__name__)


def get_next_hand(logger: logging.Logger | None = None) -> app.models.Hand | None:
    if logger is None:
        logger = logging.getLogger(__name__)

    expression = django.db.models.Q(pk__in=[])
    for direction in app.models.common.attribute_names:
        expression |= django.db.models.Q(**{f"{direction}__allow_bot_to_play_for_me": True})

    # TODO -- this isn't quite right. What we *really* want is to consider only those hands for whom the current seat is
    # controlled by a bot.  But the below sometimes gets us a hand whose current seat is controlled by a human, and that
    # basically prevents us from doing any other work.
    all_hands_with_bots = (
        app.models.Hand.objects.prepop()
        .filter(
            expression,
            is_complete=False,
            abandoned_because__isnull=True,
            board__tournament__completed_at__isnull=True,
            board__tournament__play_completion_deadline__gt=django.utils.timezone.now(),
        )
        .order_by("last_action_time")
    )

    # "manually" find the oldest hand whose current seat is controlled by the bot.  ideally we'd have the database do
    # this for us, rather than doing it here in Python; but it's not clear if that's possible.
    h: app.models.Hand
    for h in all_hands_with_bots:
        s = h.next_seat_to_call or h.next_seat_to_play

        if s is None:
            continue
        player = h.player_who_controls_seat(s, right_this_second=True)
        if player.allow_bot_to_play_for_me:
            return h

    return None


# adapted from https://stackoverflow.com/a/26092256


class LessAnnoyingLogger:
    def __init__(self):
        self._reset()
        self.current_hand = None

    def _reset(self):
        self.invocations = 0

    def note_current_hand(self, hand):
        self.current_hand = hand

    def __getattr__(self, attr):
        self.invocations += 1
        if self.invocations.bit_count() == 1:  # i.e., it's a power of two
            meth = getattr(logger, attr)

            # Crude hack to get the current hand into each log message.
            def amended_method(*args, **kwargs):
                args = list(args)
                args[0] = f"hand {self.current_hand.pk}: " + args[0]
                return meth(*args, **kwargs)

            if self.current_hand is None:
                return meth

            return amended_method
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
            hand_to_play = get_next_hand(logger=self.quiet_logger)
            self.quiet_logger.note_current_hand(hand_to_play)

            if hand_to_play is None:
                self.quiet_logger.info("No playable hand; waiting")
                time.sleep(1)
                continue

            self.wait_for_tempo(hand_to_play)
            xscript: HandTranscript = hand_to_play.get_xscript()

            if (p := hand_to_play.player_who_may_call) is not None:
                self.quiet_logger.info("%s", f"It is {p.name}'s turn to call")
                if p.allow_bot_to_play_for_me:
                    call = xscript.auction.random_legal_call()
                    hand_to_play.add_call(call=call)
                    self.quiet_logger._reset()
                    self.quiet_logger.info(
                        "%s",
                        f"I called {call} for {p.name} at {hand_to_play.direction_letters_by_player[p]}",
                    )
                else:
                    self.quiet_logger.info("%s", f"{p.name} is human")
                    time.sleep(hand_to_play.board.tournament.tempo_seconds)
            elif (s := hand_to_play.next_seat_to_play) is not None:
                self.quiet_logger.info("%s", f"It is {s.name}'s turn to play")
                p = hand_to_play.player_who_controls_seat(s, right_this_second=True)
                if p.allow_bot_to_play_for_me:
                    self.quiet_logger._reset()
                    card = xscript.slightly_less_dumb_play().card
                    hand_to_play.add_play_from_model_player(player=p, card=card)
                    self.quiet_logger.info("%s", f"I played {card} for {p.name} at {s.name}")
                else:
                    self.quiet_logger.info(
                        "%s",
                        f"{p.name} may not play now: {p.allow_bot_to_play_for_me=}.",
                    )
                    time.sleep(hand_to_play.board.tournament.tempo_seconds)
            else:
                raise Exception(
                    "This is confusing -- supposedly this hand is in progress, but nobody can call or play"
                )
