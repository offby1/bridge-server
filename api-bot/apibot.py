from __future__ import annotations

import json
import logging
import sys
from typing import Any

import requests
import retrying  # type: ignore
from sseclient import SSEClient  # type: ignore

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


def dispatch(msg: Any, session: requests.Session) -> None:
    if msg.data:
        data = json.loads(msg.data)
        if all(key in data for key in ("table", "player", "card")):
            logger.debug(
                "Player %s at table %s played %s",
                data["player"],
                data["table"],
                data["card"],
            )
        elif all(key in data for key in ("table", "player", "call")):
            logger.debug(
                "Player %s at table %s called %s",
                data["player"],
                data["table"],
                data["call"],
            )
    else:
        logger.debug("%s", vars(msg))


def _run_forever() -> None:
    host = "https://erics-work-macbook-pro.tail571dc2.ts.net/"
    logger.debug("Connecting to %s", host)

    my_name = "bob"
    session = requests.Session()
    session.auth = (my_name, ".")

    response = session.get(f"{host}/api/players/")
    response.raise_for_status()

    all_players = response.json()
    for p in all_players:
        if p["name"] == my_name:
            table = session.get(p["table"]).json()
            logger.info(f"{my_name=} {table=}")
            break
    else:
        msg = f"Cannot find user named {my_name=}"
        raise Exception(msg)

    while True:
        current_hand = session.get(table["current_hand"]).json()
        messages = SSEClient(
            f"{host}/events/hand/{current_hand['pk']}",
        )
        logger.debug("Connected to %s.", host)
        for msg in messages:
            dispatch(msg, session)
            if something_tells_me_this_hand_is_over(msg):
                break


run_forever = retrying.retry(
    retry_on_exception=_request_ex_filter,
    wait_exponential_multiplier=1000,
)(_run_forever)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    run_forever()
