import logging
import sys

import requests
import retrying  # type: ignore
from sseclient import SSEClient  # type: ignore

logger = logging.getLogger(__name__)


def _request_ex_filter(ex: Exception) -> bool:
    rv = isinstance(ex, (requests.exceptions.HTTPError, requests.exceptions.ConnectionError))
    sys.stderr.write(f"Caught {ex}; {'will' if rv else 'will not'} retry\n")
    return rv


def _run_forever() -> None:
    host = "https://erics-work-macbook-pro.tail571dc2.ts.net/"
    logger.debug("Connecting to %s", host)

    my_name = "ana"
    all_players = requests.get(f"{host}/api/players/", auth=(my_name, ".")).json()
    for p in all_players:
        if p["name"] == my_name:
            table = requests.get(p["table"], auth=(my_name, ".")).json()
            logger.info(f"{my_name=} {table=}")
            break
    else:
        msg = f"Cannot find user named {my_name=}"
        raise Exception(msg)

    messages = SSEClient(
        f"{host}/events/table/{table['pk']}",
    )
    logger.debug("Connected to %s.", host)
    for msg in messages:
        logger.debug("%s", vars(msg))


run_forever = retrying.retry(
    retry_on_exception=_request_ex_filter,
    wait_exponential_multiplier=1000,
)(_run_forever)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    run_forever()
