import time

from django.core.management.base import BaseCommand
from django.utils.timezone import now

import app.models
from bridge.xscript import HandTranscript


class Command(BaseCommand):
    def wait_for_tempo(self, hand_to_play: app.models.Hand) -> None:
        tempo = hand_to_play.board.tournament.tempo_seconds
        last_action_time = hand_to_play.modified.timestamp()
        wait_until = last_action_time + tempo
        now = time.time()
        time.sleep(max(0, wait_until - now))

    def handle(self, *_args, **_options) -> None:
        while True:
            hand_to_play: app.models.Hand = (
                app.models.Hand.objects.filter(
                    is_complete=False,
                    abandoned_because__isnull=True,
                    board__tournament__completed_at__isnull=True,
                    board__tournament__signup_deadline__lt=now(),
                )
                .order_by("-modified")
                .first()
            )
            if hand_to_play is None:
                self.stderr.write("No playable hand; sleeping")
                time.sleep(1)
                continue
            self.stderr.write(f"Will call or play at {hand_to_play}")
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
