from __future__ import annotations

import collections
import contextlib
import datetime
import functools
import json
import operator
import os
import random
import sys
import time
import typing

import bridge.card
import bridge.xscript
import requests
import retrying  # type: ignore
from app.models import AuctionError, Hand, Player, Table
from app.models.utils import assert_type
from bridge.contract import Contract, Pass
from django.conf import settings
from django.core.management.base import BaseCommand
from sseclient import SSEClient  # type: ignore

random.seed(0)


def ts(time_t=None):
    if time_t is None:
        time_t = time.time()
    return datetime.datetime.fromtimestamp(time_t, tz=datetime.timezone.utc)


def _request_ex_filter(ex):
    rv = isinstance(ex, (requests.exceptions.HTTPError, requests.exceptions.ConnectionError))
    now = ts().replace(microsecond=0).isoformat()
    sys.stderr.write(f"{now} Caught {ex}; {'will' if rv else 'will not'} retry\n")
    return rv


def trick_taking_power(c: bridge.card.Card, *, xscript: bridge.xscript.HandTranscript) -> int:
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

    t = xscript.table

    me = xscript.player
    lho = t.get_lho(me)
    rho = t.get_lho(t.get_partner(me))

    hidden_opponents_hands_to_consider = [lho, rho]

    opponents_cards_in_current_trick: list[bridge.card.Card] = []
    if xscript.tricks and not xscript.tricks[-1].is_complete():
        for play in xscript.tricks[-1]:
            if play.player in (lho, rho):
                hidden_opponents_hands_to_consider.remove(play.player)
                opponents_cards_in_current_trick.append(play.card)

    cards_in_opponents_hands: list[bridge.card.Card] = []
    for opp in hidden_opponents_hands_to_consider:
        cards_in_opponents_hands.extend(opp.hand.cards)

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
    def __init__(self, *args, **kwargs):
        self.table = None
        super().__init__(*args, **kwargs)

    def log(self, string: str) -> None:
        final = f"{self.table=} {string}"
        self.stdout.write(final)
        self.stdout.flush()

    @contextlib.contextmanager
    def delayed_action(self, *, table):
        previous_action_time = self.last_action_timestamps_by_table_id[table.pk]
        sleep_until = previous_action_time + 0.25

        if (duration := sleep_until - time.time()) > 0:
            # TODO -- if duration is zero, log a message somewhere?  Or, if it's zero *a lot*, log that, since it would
            # imply we're falling behind.
            time.sleep(duration)

        yield
        self.last_action_timestamps_by_table_id[table.pk] = time.time()

    def skip_player(self, *, table: Table, player: Player) -> bool:
        if player is None:
            self.log("player is None -- auction or play must be over.")
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
            return

        if self.skip_player(table=table, player=modplayer):
            return

        player_to_impersonate = modplayer.libraryThing
        a = table.current_auction

        call = a.random_legal_call()

        # Try a few times to find something other than "pass", since a passed-out auction isn't interesting.
        if [pc.call for pc in a.player_calls] == [Pass, Pass, Pass]:
            for _ in range(5):
                call = a.random_legal_call()
                self.stderr.write(f"In loop, got {call=}")
                if call != Pass:
                    self.stderr.write("Gudenov")
                    break
                self.stderr.write("Nuts, a pass! Let's try again")
            else:
                self.log(
                    "I tried rilly rilly hard not to pass this hand out, but ... 😢  I'll get a new board!"
                )
                # TODO -- it'd probably be cleaner to do nothing here, and instead have the server send a "the hand was
                # passed out" event, analagous to the "contract_text" message that it currently sends when an auction
                # has settled, and then have our "dispatch" fetch the next board.
                with self.delayed_action(table=table):
                    table.next_board()
                return

        try:
            hand.add_call_from_player(player=player_to_impersonate, call=call)
        except AuctionError as e:
            # The one time I saw this was when I clicked on a blue bidding box as soon as it appeared.  Then the
            # add_call_from_player call above discovered that the player_to_impersonate was out of turn.
            self.stderr.write(f"Uh-oh -- {e}")
        else:
            self.log(
                f"Just impersonated {player_to_impersonate}, and said {call} on their behalf",
            )

    def make_a_groovy_play(self, *, hand: Hand) -> None:
        if not hand.auction.found_contract:
            return

        table = hand.table

        seat_to_impersonate = table.next_seat_to_play

        if seat_to_impersonate is None:
            return

        if self.skip_player(table=table, player=seat_to_impersonate.player):
            return

        legal_cards = hand.xscript.legal_cards()
        if not legal_cards:
            self.log(f"No legal cards at {seat_to_impersonate}? The hand must be over.")
            return

        chosen_card = hand.xscript.slightly_less_dumb_play(
            order_func=functools.partial(trick_taking_power, xscript=hand.xscript)
        )

        ranked_options = sorted(
            [(c, trick_taking_power(c, xscript=hand.xscript)) for c in hand.xscript.legal_cards()],
            key=operator.itemgetter(1),
        )
        p = hand.add_play_from_player(player=hand.xscript.player, card=chosen_card)
        self.log(f"{p} out of {ranked_options=}")

    def dispatch(self, *, data: dict[str, typing.Any]) -> None:
        self.log(f"<-- {data}")

        try:
            table = Table.objects.get(pk=data.get("table"))
        except Table.DoesNotExist:
            self.stderr.write(f"In {data}, table {data.get('table')=} does not exist")
            return

        self.table = table

        # In a perfect world, the event on which we're dispatching would include a timestamp, and we'd use *that*
        # instead of `time.time`.  But oh well.
        self.last_action_timestamps_by_table_id[table.pk] = time.time()

        if data.get("action") in ("just formed", "new hand") or set(data.keys()) == {
            "table",
            "player",
            "call",
        }:
            with self.delayed_action(table=table):
                self.make_a_groovy_call(hand=table.current_hand)

        elif {"table", "contract"}.issubset(data.keys()) or {
            "table",
            "player",
            "card",
        }.issubset(data.keys()):
            with self.delayed_action(table=table):
                self.make_a_groovy_play(hand=table.current_hand)
        elif set(data.keys()) == {"table", "direction", "action"}:
            self.log(f"I believe I been poked: {data=}")
            with self.delayed_action(table=table):
                self.make_a_groovy_call(hand=table.current_hand)
                self.make_a_groovy_play(hand=table.current_hand)
        elif "final_score" in data:
            self.log(
                "I guess this table's play is done, so I should poke that GIMME NEW BOARD button"
            )
            with self.delayed_action(table=table):
                table.next_board()
        else:
            self.stderr.write(f"No idea what to do with {data=}")

    @retrying.retry(
        retry_on_exception=_request_ex_filter,
        wait_exponential_multiplier=1000,
    )
    def run_forever(self):
        self.log(f"{settings.EVENTSTREAM_REDIS=}")
        django_host = os.environ.get("DJANGO_HOST", "localhost")
        self.log(f"Connecting to {django_host}")

        messages = SSEClient(
            f"http://{django_host}:9000/events/all-tables/",
        )
        self.log(f"Finally! Connected to {django_host}.")
        for msg in messages:
            self.log(str(vars(msg)))
            if msg.event != "keep-alive":
                if msg.data:
                    data = json.loads(msg.data)
                    self.dispatch(data=data)
                else:
                    self.log(f"message with no data: {vars(msg)=}")

    def handle(self, *args, **options):
        self.last_action_timestamps_by_table_id = collections.defaultdict(lambda: 0)

        with contextlib.suppress(KeyboardInterrupt):
            self.run_forever()
