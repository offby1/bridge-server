from __future__ import annotations

import collections
import contextlib
import datetime
import functools
import json
import logging
import operator
import os
import random
import sys
import time
import typing

import bridge.card
import bridge.table
import bridge.xscript
import requests
import retrying  # type: ignore
from app.models import AuctionError, Hand, Player, Table, TableException
from app.models.utils import assert_type
from bridge.contract import Contract, Pass
from django.conf import settings
from django.core.management.base import BaseCommand
from sseclient import SSEClient  # type: ignore

random.seed(0)

logger = logging.getLogger("bot")


def ts(time_t=None):
    if time_t is None:
        time_t = time.time()
    return datetime.datetime.fromtimestamp(time_t, tz=datetime.timezone.utc)


def _request_ex_filter(ex):
    rv = isinstance(ex, (requests.exceptions.HTTPError, requests.exceptions.ConnectionError))
    now = ts().replace(microsecond=0).isoformat()
    sys.stderr.write(f"{now} Caught {ex}; {'will' if rv else 'will not'} retry\n")
    return rv


def trick_taking_power(c: bridge.card.Card, *, hand: Hand) -> int:
    """
    Roughly: how many opponent's cards rank higher than this one?  Only look at opponents who haven't yet played to this trick.
    Return that value, negated.  If there's a trump suit, those count too.
    Examples:
    - at notrump, opening lead is the club 2, declarer & dummy have (say) six clubs.
      All six beat the club two, so our value is -6.
    - at one diamond, halfway through the hand, someone plays the 8 of spades.
      - opponents have (say) 2, 3, and ten of spades, and 3 diamonds.
      - our value is thus -1 * (1 for the ten of spades plus 3 for each diamond) == -4.
    - at notrump, if we play a card of whose suit we've stripped the opponents, its power is 0 (the maximum possible).
    """
    assert_type(c, bridge.card.Card)

    t: bridge.table.Table = hand.table.libraryThing

    xscript = hand.get_xscript()
    me = xscript.current_named_seat()
    lho: bridge.seat.Seat = t.get_lho_seat(me.seat)
    rho: bridge.seat.Seat = t.get_partner_seat(lho)

    hidden_opponents_seats_to_consider = [lho, rho]

    opponents_cards_in_current_trick: list[bridge.card.Card] = []
    if xscript.tricks and not xscript.tricks[-1].is_complete():
        for play in xscript.tricks[-1]:
            if play.seat in (lho, rho):
                hidden_opponents_seats_to_consider.remove(play.seat)
                opponents_cards_in_current_trick.append(play.card)

    cards_in_opponents_hands: list[bridge.card.Card] = []
    for _opp_seat in hidden_opponents_seats_to_consider:
        opps_hand = hand.board.cards_for_direction(_opp_seat.value)
        cards_in_opponents_hands.extend(opps_hand)

    assert isinstance(xscript.auction.status, Contract)

    powah = 0

    for oppo in cards_in_opponents_hands + opponents_cards_in_current_trick:
        assert_type(oppo, bridge.card.Card)

        # TODO -- this doesn't seem quite right.  If oppo is a trump card, and c is not, oppo will win *only* if either
        # - trumps were led; or
        # - opponents have a void in our suit, so they can legally play the trump
        # But they cannot always play the trump, so it doesn't seem right to count it as a full minus one here.
        if xscript.would_beat(candidate=oppo, subject=c):
            powah -= 1
    return powah


class Command(BaseCommand):
    # https://docs.python.org/3.12/howto/logging-cookbook.html#filters-contextual
    class ContextFilter:
        def __init__(self, table: Table) -> None:
            self.table = table

        def filter(self, record: logging.LogRecord) -> bool:
            if self.table is not None:
                hand = self.table.current_hand
                board = hand.board
                record.msg = f"{self.table} hand {hand.pk} board {board.pk}: {record.msg}"
            else:
                record.msg = f"(no table): {record.msg}"

            return True

    def __init__(self, *args, **kwargs):
        logging.basicConfig(
            # https://docs.python.org/3.12/library/logging.html#logrecord-attributes
            format="{asctime} {levelname:5} {filename} {lineno} {message}",
            level=logging.INFO,
            datefmt="%Y-%m-%dT%H:%M:%S%z",
            style="{",
        )

        logger.setLevel(logging.DEBUG)

        self.loggingFilter = self.ContextFilter(None)
        logger.addFilter(self.loggingFilter)

        self.last_action_timestamps_by_table_id = collections.defaultdict(lambda: 0)
        self.action_queue = []
        super().__init__(*args, **kwargs)

    def delay_action(self, *, table: Table, func) -> None:
        previous_action_time = self.last_action_timestamps_by_table_id[table.pk]
        sleep_until = previous_action_time + 0.25

        # Schedule the action for the future
        self.action_queue.insert(0, (sleep_until, table.pk, func))

        # Do whatever action comes next

        sleep_until, table_pk, func = self.action_queue.pop(-1)

        if (duration := sleep_until - time.time()) > 0:
            # TODO -- if duration is zero, log a message somewhere?  Or, if it's zero *a lot*, log that, since it would
            # imply we're falling behind.
            time.sleep(duration)

        func()
        self.last_action_timestamps_by_table_id[table_pk] = time.time()

    def skip_player(self, *, table: Table, player: Player) -> bool:
        if player is None:
            logger.info("player is None -- auction or play must be over.")
            return True

        dummy_seat = table.dummy
        declarer_seat = table.declarer
        if declarer_seat is not None and player.most_recent_seat == dummy_seat:
            return self.skip_player(table=table, player=declarer_seat.player)

        return bool(not player.allow_bot_to_play_for_me)

    def make_a_groovy_call(self, *, hand: Hand) -> None:
        table = hand.table
        modplayer = hand.player_who_may_call

        if modplayer is None:
            logger.debug(f"{modplayer=}, so returning")
            return

        if self.skip_player(table=table, player=modplayer):
            logger.debug(f"{self.skip_player(table=table, player=modplayer)=}, so returning")
            return

        player_to_impersonate = modplayer.libraryThing(hand=hand)
        a = table.current_auction

        call = a.random_legal_call()

        # Try a few times to find something other than "pass", since a passed-out auction isn't interesting.
        if [pc.call for pc in a.player_calls] == [Pass, Pass, Pass]:
            for _ in range(5):
                call = a.random_legal_call()

                if call != Pass:
                    break

            else:
                logger.info("I tried rilly rilly hard not to pass this hand out, but ... 😢")

        try:
            hand.add_call_from_player(player=player_to_impersonate, call=call)
        except AuctionError as e:
            # The one time I saw this was when I clicked on a blue bidding box as soon as it appeared.  Then the
            # add_call_from_player call above discovered that the player_to_impersonate was out of turn.
            self.stderr.write(f"Uh-oh -- {e}")
        else:
            logger.info(
                f"Just impersonated {player_to_impersonate}, and said {call} on their behalf",
            )

    def make_a_groovy_play(self, *, modHand: Hand) -> None:
        if not modHand.auction.found_contract:
            return

        table = modHand.table

        seat_to_impersonate = table.next_seat_to_play

        if seat_to_impersonate is None:
            return

        if self.skip_player(table=table, player=seat_to_impersonate.player):
            return

        libHand = bridge.table.Hand(
            cards=sorted(modHand.current_cards_by_seat()[seat_to_impersonate.libraryThing])
        )
        legal_cards = modHand.get_xscript().legal_cards(some_hand=libHand)
        if not legal_cards:
            logger.info(
                f"No legal cards at {seat_to_impersonate}? The hand must be over.",
            )
            return

        chosen_card = modHand.get_xscript().slightly_less_dumb_play(
            order_func=functools.partial(trick_taking_power, hand=modHand), some_hand=libHand
        )

        ranked_options = sorted(
            [
                (c, trick_taking_power(c, hand=modHand))
                for c in modHand.get_xscript().legal_cards(some_hand=libHand)
            ],
            key=operator.itemgetter(1),
        )
        p = modHand.add_play_from_player(
            player=seat_to_impersonate.player.libraryThing(hand=modHand), card=chosen_card
        )
        logger.info(f"{p} out of {ranked_options=}")

    def dispatch(self, *, data: dict[str, typing.Any]) -> None:
        logger.info(f"<-- {data}")

        table_pk = None

        # Where can we find the table primary key?  It's in different "places" in different events.
        if (new_call := data.get("new-call")) is not None:
            table_pk = new_call["hand"]["table"]
        elif (new_play := data.get("new-play")) is not None:
            table_pk = new_play["hand"]["table"]
        elif (new_hand := data.get("new-hand")) is not None:
            table_pk = new_hand["table"]

        if (
            table_pk is None
        ):  # fallback; to be deleted once I 'rationalize' all the events that come from db inserts
            table_pk = data.get("table")

        if table_pk is None:
            self.stderr.write(f"In {data}, I don't have a clue, Lieutenant, where the table PK is")
            return

        try:
            table = Table.objects.get(pk=table_pk)
        except Table.DoesNotExist:
            self.stderr.write(f"In {data}, table with {table_pk=} does not exist")
            return

        self.loggingFilter.table = table

        if (when := data.get("time")) is not None:
            self.last_action_timestamps_by_table_id[table.pk] = when
        elif data.get("action") != "pokey pokey":
            msg = f"{data=} aint' got no timestamp! I'm outta here."
            raise Exception(msg)

        if (
            data.get("action") == "just formed"
            or data.get("new-hand") is not None
            or data.get("new-call") is not None
        ):
            self.delay_action(
                table=table, func=lambda: self.make_a_groovy_call(hand=table.current_hand)
            )
        elif data.get("new-play") is not None or "contract_text" in data:
            self.delay_action(
                table=table, func=lambda: self.make_a_groovy_play(modHand=table.current_hand)
            )
        elif {"table", "direction", "action"}.issubset(data.keys()):
            logger.info(f"I believe I been poked: {data=}")
            self.delay_action(
                table=table, func=lambda: self.make_a_groovy_call(hand=table.current_hand)
            )
            self.delay_action(
                table=table, func=lambda: self.make_a_groovy_play(modHand=table.current_hand)
            )
        elif "final_score" in data or {"table", "passed_out"}.issubset(data.keys()):
            logger.info(
                f"I guess this table's play is done ({data}), so I should poke that GIMME NEW BOARD button",
            )
            try:
                self.delay_action(table=table, func=table.next_board)
            except TableException as e:
                logger.info(f"{e}; I will guess the tournament is over.")

        else:
            logger.info(f"No idea what to do with {data=}")

    @retrying.retry(
        retry_on_exception=_request_ex_filter,
        wait_exponential_multiplier=1000,
    )
    def run_forever(self):
        logger.info(f"{settings.EVENTSTREAM_REDIS=}")
        django_host = os.environ.get("DJANGO_HOST", "localhost")
        logger.info(f"Connecting to {django_host}")

        messages = SSEClient(
            f"http://{django_host}:9000/events/all-tables/",
        )
        logger.info(f"Finally! Connected to {django_host}.")
        for msg in messages:
            self.loggingFilter.table = None

            if msg.event != "keep-alive":
                if msg.data:
                    data = json.loads(msg.data)
                    self.dispatch(data=data)
                else:
                    logger.info(f"message with no data: {vars(msg)=}")

    def handle(self, *args, **options):
        with contextlib.suppress(KeyboardInterrupt):
            self.run_forever()
