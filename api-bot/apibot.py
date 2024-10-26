from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING, Any

import requests
import retrying  # type: ignore
from sseclient import SSEClient  # type: ignore

if TYPE_CHECKING:
    from bridge.xscript import HandTranscript

logger = logging.getLogger(__name__)


def _request_ex_filter(ex: Exception) -> bool:
    if isinstance(ex, requests.exceptions.HTTPError):
        response = ex.response
        if response.status_code < 500:
            # not worth retrying
            return False

    rv = isinstance(ex, (requests.exceptions.HTTPError, requests.exceptions.ConnectionError))
    sys.stderr.write(f"Caught {ex}; {'will' if rv else 'will not'} retry\n")
    return rv


current_xscript: HandTranscript | None = None


# a return of True means "this hand is over; time to listen for events from a new one"
def dispatch_hand_action(msg: Any, session: requests.Session) -> bool:
    global current_xscript

    if msg.data:
        data = json.loads(msg.data)
        if all(key in data for key in ["new-play"]):
            logger.debug(
                "Seat %s at table %s played %s",
                data["new-play"]["seat_pk"],
                data["new-play"]["hand"]["table"],
                data["new-play"]["serialized"],
            )
        elif all(key in data for key in ["new-call"]):
            logger.debug(
                "Seat %s at table %s called %s",
                data["new-call"]["seat_pk"],
                data["new-call"]["hand"]["table"],
                data["new-call"]["serialized"],
            )
        elif (new_hand := data.get("new-hand")) is not None:
            logger.debug("Ah! The hand is over; here's the new hand %s", new_hand)
            # example_hand = {"pk": 1, "table": 1, "board": 1}
            # example_board = {
            #     "east_cards": "♣Q♣K♦3♦4♦6♦9♥5♥T♥J♠2♠5♠7♠A",
            #     "ew_vulnerable": False,
            #     "north_cards": "♣2♣3♣6♣7♣9♣A♥4♥9♥Q♥A♠4♠8♠Q",
            #     "ns_vulnerable": False,
            #     "pk": 1,
            #     "south_cards": "♣5♣8♣T♣J♦7♦T♦Q♥3♠3♠6♠9♠T♠K",
            #     "west_cards": "♣4♦2♦5♦8♦J♦K♦A♥2♥6♥7♥8♥K♠J",
            # }
            # current_xscript = HandTranscript(table=..., auction=..., ns_vuln=..., ew_vuln=...)
            return True

        else:
            logger.warning("OK, I have no idea what to do with %s", data)

    else:
        logger.debug("No data in %s?", vars(msg))

    return False


# TODO -- write some API call that simply fetches a player by name.
def find_my_player_json_thingy(
    *, session: requests.Session, host: str, my_name: str
) -> dict[str, str]:
    url = f"{host}/api/players/"
    response = session.get(url)
    response.raise_for_status()

    all_players = response.json()
    for p in all_players:
        if p["name"] == my_name:
            return p
    msg = f"er, uh, I can't find {my_name} in the output from {url}"
    raise Exception(msg)


def _run_forever() -> None:
    host = "https://erics-work-macbook-pro.tail571dc2.ts.net/"
    logger.debug("Connecting to %s", host)

    my_name = "bob"
    session = requests.Session()
    session.auth = (my_name, ".")

    p = find_my_player_json_thingy(
        session=session, host=host, my_name=my_name
    )  # n.b. https://www.youtube.com/watch?v=g2Xk_dTn2x4&t=27s
    my_table_url = p["current_table"]

    while True:
        table = session.get(
            my_table_url
        ).json()  # we keep fetching this because it changes with each new hand
        logger.info(f"{my_name=} {table=}")
        current_hand_url = table["current_hand"]
        current_hand_pk = session.get(current_hand_url).json()["pk"]
        # how tf do I know what seat I'm at?
        # - we've already fetched player data; it's in `p`
        # - check "seat_set"; that's a list of URLs
        # - each seat has a player URL
        # - could probably cheat and not fetch the player URL, and instead compare it to the one we already fetched
        events_url = f"{host}/events/player/system:player:{p['pk']}/"
        logger.info(f"{current_hand_url=} {current_hand_pk=}; fetching events from {events_url}")
        messages = SSEClient(events_url)

        for msg in messages:
            if dispatch_hand_action(msg, session):
                break


run_forever = retrying.retry(
    retry_on_exception=_request_ex_filter,
    wait_exponential_multiplier=1000,
)(_run_forever)

if __name__ == "__main__":
    logging.basicConfig(
        # https://docs.python.org/3/library/logging.html#logrecord-attributes
        format="{asctime} {levelname:5} {name} {filename} {lineno} {funcName} {message}",
        level=logging.DEBUG,
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        style="{",
    )
    run_forever()
