"""Play one hand start to finish, narrating each call and play to stdout.

This is a stepping stone towards docs/ai-bot-plan.md's AI-backed bot: it drives the
exact same bridge-library calls (`make_standard_american_call`,
`slightly_less_dumb_play`) that will eventually get replaced with an Anthropic API
call, so the surrounding loop -- find whose turn it is, narrate the decision, apply
it, notice when the contract is set, notice when the hand is done -- doesn't have to
be rewritten later.

Unlike `cheating_bot.py`, this ignores `allow_bot_to_play_for_me` and plays every
seat unconditionally, and it drives one specific hand to completion rather than
polling the whole system forever. It's a local demo/dev tool: point it at a real
hand with human players and it will cheerfully play their cards for them.
"""

from __future__ import annotations

import logging
import time

from bridge.contract import Contract
from django.core.management.base import BaseCommand, CommandError

import app.models


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--hand",
            type=int,
            default=None,
            help="pk of the hand to play. Defaults to the most recently created incomplete hand.",
        )
        parser.add_argument(
            "--tempo-seconds",
            type=float,
            default=None,
            help=(
                "Pause this long between moves, so a human can follow along. "
                "Defaults to the hand's tournament's own tempo_seconds."
            ),
        )

    def handle(self, *args, **options) -> None:
        # Hand.add_call()/add_play_from_model_player() log a DEBUG line per move, which
        # would otherwise drown out our own narration under dev/test logging settings.
        logging.getLogger("app.models.hand").setLevel(logging.WARNING)

        hand = self._find_hand(options["hand"])
        tempo = options["tempo_seconds"]
        if tempo is None:
            tempo = hand.board.tournament.tempo_seconds

        self.stdout.write(f"Playing hand {hand.pk} ({hand.board}) to completion.\n")

        contract_announced = False

        while True:
            xscript = hand.get_xscript()
            if xscript.is_complete():
                break

            if not isinstance(xscript.auction.status, Contract):
                self._make_a_call(hand, xscript)
            else:
                if not contract_announced:
                    self._announce_contract(xscript.auction.status)
                    contract_announced = True
                self._play_a_card(hand, xscript)

            time.sleep(tempo)

        self._announce_final_score(hand.get_xscript())

    def _find_hand(self, pk: int | None) -> app.models.Hand:
        if pk is not None:
            try:
                return app.models.Hand.objects.get(pk=pk)
            except app.models.Hand.DoesNotExist:
                raise CommandError(f"No hand with pk {pk}") from None

        hand = (
            app.models.Hand.objects.filter(is_complete=False, abandoned_because__isnull=True)
            .order_by("-pk")
            .first()
        )
        if hand is None:
            raise CommandError(
                "No incomplete hand found. Try `just fixture usual_setup` to load one, "
                "then re-run this without --hand."
            )
        return hand

    def _make_a_call(self, hand: app.models.Hand, xscript) -> None:
        seat = xscript.auction.allowed_caller().seat
        call = xscript.auction.make_standard_american_call(
            pbn=xscript.endplay_deal.to_pbn(),
            vuln=xscript.endplay_vulnerability(),
        )
        self.stdout.write(f"{seat}: {call}\n")
        hand.add_call(call=call)

    def _announce_contract(self, contract: Contract) -> None:
        double_description = ""
        if contract.multiplier == 2:
            double_description = ", doubled"
        elif contract.multiplier == 4:
            double_description = ", redoubled"
        self.stdout.write(
            f"\nOK, the contract is {contract.bid}{double_description}, "
            f"played by {contract.declarer.name} (sitting {contract.declarer.seat}).\n\n"
        )

    def _play_a_card(self, hand: app.models.Hand, xscript) -> None:
        seat = xscript.next_seat_to_play()
        player = hand.player_who_controls_seat(seat, right_this_second=True)

        current_trick = xscript.tricks[-1] if xscript.tricks else None
        if current_trick is not None and current_trick.is_complete():
            current_trick = None
        num_played_this_trick = len(current_trick) if current_trick is not None else 0

        if num_played_this_trick == 0:
            reason = "leading; picking a safe low card"
        elif num_played_this_trick == 2:
            reason = "it's third hand, so playing high"
        else:
            reason = "playing low for now"

        play = xscript.slightly_less_dumb_play()
        self.stdout.write(f"{seat}: plays {play.card} ({reason})\n")
        hand.add_play_from_model_player(player=player, card=play.card)

    def _announce_final_score(self, xscript) -> None:
        self.stdout.write(f"\nHand complete. Score: {xscript.final_score()}\n")
