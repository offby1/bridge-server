from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any, Iterable

import more_itertools
import requests
import retrying  # type: ignore [import-untyped]
from bridge.auction import Auction
from bridge.card import Card
from bridge.contract import Bid
from bridge.seat import Seat
from bridge.table import Hand, Player, Table
from bridge.xscript import HandTranscript
from sseclient import SSEClient  # type: ignore [import-untyped]

logger = logging.getLogger("apibot")

Blob = dict[str, Any]  # the type of the stuff we get from the API


def _request_ex_filter(ex: Exception) -> bool:
    if isinstance(ex, requests.exceptions.HTTPError):
        response = ex.response
        if response.status_code < 500:
            # not worth retrying
            return False

    return isinstance(ex, (requests.exceptions.HTTPError, requests.exceptions.ConnectionError))


current_xscript: HandTranscript | None = None


def players_from_board(board: Blob) -> Iterable[Player]:
    # do we really care what the player's names are?  We might, but for now let's just avoid another API call and make shit up.
    for index, name in enumerate(["north", "east", "south", "west"]):
        seat = Seat(index + 1)
        hand = Hand(
            cards=[
                Card.deserialize("".join(c))
                for c in more_itertools.chunked(board[f"{name}_cards"], 2)
            ]
        )
        yield Player(name=name, hand=hand, seat=seat)


# an integer return value means "this hand is over; here's the pk of the new one, so you can listen for events from it"
def dispatch_hand_action(
    *, msg: Any, session: requests.Session, current_seat_pk: int
) -> int | None:
    global current_xscript

    if msg.data:
        data = json.loads(msg.data)
        logger.debug("<-- %r", data)
        if all(key in data for key in ["new-play"]):
            logger.debug(
                "Seat %s at table %s played %s",
                data["new-play"]["seat_pk"],
                data["new-play"]["hand"]["table"],
                data["new-play"]["serialized"],
            )

            # TODO -- This can happen if we missed notifications :-(
            assert current_xscript is not None

            current_xscript.add_card(Card.deserialize(data["new-play"]["serialized"]))
            if izzit_my_turn(current_xscript):
                make_a_play()
            return None
        if all(key in data for key in ["new-call"]):
            logger.debug(
                "Seat %s at table %s called %s",
                data["new-call"]["seat_pk"],
                data["new-call"]["hand"]["table"],
                data["new-call"]["serialized"],
            )
            assert current_xscript is not None
            current_xscript.add_call(Bid.deserialize(data["new-call"]["serialized"]))
            if izzit_my_turn(current_xscript):
                make_a_call()
            return None
        if (new_hand := data.get("new-hand")) is not None:
            if current_xscript is not None:
                logger.info(current_xscript.final_score())
            logger.debug("Ah! The hand is over; here's the new hand %s", new_hand)
            board = new_hand["board"]

            table = Table(players=list(players_from_board(board)))
            print(f"OK, I know {current_seat_pk=} and {table=}; how do I link 'em up")
            auction = Auction(table=table, dealer=Seat(board["dealer"]))
            current_xscript = HandTranscript(
                table=table,
                auction=auction,
                ns_vuln=board["ns_vulnerable"],
                ew_vuln=board["ew_vulnerable"],
            )
            return new_hand["pk"]

        logger.warning("OK, I have no idea what to do with %s", data)
        return None

    logger.debug("No data in %s?", vars(msg))
    return None


def find_my_player_json_thingy(*, session: requests.Session, host: str, my_name: str) -> Blob:
    url = urllib.parse.urlparse(host)
    url = url._replace(path="/api/players/", query=urllib.parse.urlencode({"name": my_name}))

    response = session.get(urllib.parse.urlunparse(url))

    response.raise_for_status()

    return response.json()["results"][0]


# TODO, maybe: replace me with a call to the API that queries for the seat, once such a call exists.
def find_my_seat_pk(*, session: requests.Session, player: Blob, table: Blob) -> int:
    for seat_url in table["seat_set"]:
        seat: Blob = session.get(seat_url).json()
        one_player_url = urllib.parse.urlparse(seat["player"])

        components = one_player_url.path.rsplit("/", maxsplit=2)
        if not components[-1]:
            components.pop(-1)

        candidate_last_component = components[-1]
        if candidate_last_component == str(player["pk"]):
            logger.debug("Player %s is at seat %s", player, seat["pk"])
            return seat["pk"]

    msg = f"Cannot find a player with pk ({player['pk']}) in response from {seat_url}"
    raise Exception(msg)


@retrying.retry(
    retry_on_exception=_request_ex_filter,
    wait_exponential_multiplier=1000,
    after_attempts=lambda attempt_number: logger.warning(
        "Attempt number %d failed; will retry", attempt_number
    ),
)
def run_forever() -> None:
    host = "https://erics-work-macbook-pro.tail571dc2.ts.net/"
    logger.debug("Connecting to %s", host)

    my_name = "bob"
    session = requests.Session()
    session.auth = (my_name, ".")

    p = find_my_player_json_thingy(
        session=session, host=host, my_name=my_name
    )  # n.b. https://www.youtube.com/watch?v=g2Xk_dTn2x4&t=27s
    my_table_url = p["current_table"]

    table = session.get(my_table_url).json()
    logger.info(f"{my_name=} {table=}")

    current_hand_pk = session.get(table["current_hand"]).json()["pk"]
    current_seat_pk = find_my_seat_pk(session=session, player=p, table=table)

    while True:
        events_url = f"{host}/events/player/system:player:{p['pk']}/"
        logger.info(f"{current_hand_pk=}; fetching events from {events_url}")
        messages = SSEClient(events_url)

        for msg in messages:
            if (
                new_hand_pk := dispatch_hand_action(
                    msg=msg, session=session, current_seat_pk=current_seat_pk
                )
            ) is not None:
                current_hand_pk = new_hand_pk
                break


if __name__ == "__main__":
    logging.basicConfig(
        # https://docs.python.org/3/library/logging.html#logrecord-attributes
        format="{asctime} {levelname:5} {name} {filename} {lineno} {funcName} {message}",
        level=logging.DEBUG,
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        style="{",
    )
    logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)
    run_forever()
