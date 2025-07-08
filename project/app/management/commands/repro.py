import pprint

from django.core.cache import cache
from django.core.management.base import BaseCommand

from app.management.commands.cheating_bot import get_next_hand


class Command(BaseCommand):
    def handle(self, *_args, **_options) -> None:
        for _ in range(2):
            hand_to_play = get_next_hand()

            assert hand_to_play is not None
            xscript = hand_to_play.get_xscript()
            pprint.pprint(xscript.serializable()["auction"])
            print(f"{getattr(hand_to_play.player_who_may_call, 'name', None)=}")
            print(f"{getattr(hand_to_play.player_who_may_play, 'name', None)=}")

            cache.clear()
