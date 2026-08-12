"""SSE broadcasters driven by the `notifier` command.

Every function here reproduces one model change's SSE fan-out: given the row that
changed (a Hand, a Player, a Message), it renders and sends exactly the events
the models used to send inline from `send_event`/`send_timestamped_event` call
sites. The `notifier` management command calls these in its own process, on
COMMIT, in response to a PostgreSQL NOTIFY (see docs/README.listen-notify.md).

The point of moving the sends here: a broadcast is no longer something a code
path has to remember to do. It follows from the row changing, so it cannot be
forgotten.

These broadcasters reuse `app.models.hand`'s `send_event` and
`send_timestamped_event`, so a test that patches `app.models.hand.send_event`
observes both the sends still inline in the models and the ones moved here.
"""

import time
from types import SimpleNamespace

from django.template.loader import render_to_string

import app.models.hand
from app.models.hand import send_timestamped_event
from app.sse_events import (
    SSEEventTypes,
    create_player_hand_event,
    create_table_event,
)
from bridge.contract import Contract as libContract


def broadcast_after_call(*, hand: app.models.hand.Hand) -> None:
    """Reproduce the SSE fan-out for a call having been added to `hand`.

    Formerly inline in `Hand.add_call`; driven now by the `app_call` INSERT
    trigger. The just-added call is the most recent row in `hand.call_set`.
    """
    if dummy_player := hand.model_dummy:
        # The dummy's checkbox becomes disabled once the contract is settled.
        html = render_to_string(
            "bot-checkbox.html",
            {"user": SimpleNamespace(player=dummy_player), "error_message": None},
        )
        app.models.hand.send_event(
            channel=dummy_player.bot_checkbox_channel,
            event_type=SSEEventTypes.BOT_CHECKBOX,
            data=html,
            json_encode=False,
        )

    now = time.time()

    for p in hand.players():
        send_timestamped_event(
            channel=p.event_HTML_hand_channel,
            event_type=SSEEventTypes.PLAYER_HAND,
            data=create_player_hand_event(
                bidding_box_html=hand._get_current_bidding_box_html_for_player(p),
                hand_pk=hand.pk,
                show_hint_button=p.is_my_turn_to_interact(),
            ),
            when=now,
        )

    last_call = hand.call_set.order_by("id").last()
    assert last_call is not None
    hand.send_JSON_to_players(
        event_type=SSEEventTypes.BOT_NEW_CALL,
        data={
            "hand_pk": hand.pk,
            "new-call": {
                "serialized": last_call.serialized,
                "explanation": last_call.explanation,
            },
            "tempo_seconds": hand.board.tournament.tempo_seconds,
        },
    )

    from app.views.hand import auction_history_HTML_for_table

    send_timestamped_event(
        channel=hand.event_table_html_channel,
        event_type=SSEEventTypes.TABLE,
        data=create_table_event(auction_history_html=auction_history_HTML_for_table(hand=hand)),
        when=now,
    )

    if hand.declarer:  # the auction just settled
        contract = hand.auction.status
        assert isinstance(contract, libContract)
        assert contract.declarer is not None

        data = {
            "contract_text": str(contract),
            "contract": {
                "opening_leader": contract.declarer.seat.lho().value,
            },
        }
        hand.send_JSON_to_players(event_type=SSEEventTypes.BOT_CONTRACT, data=data)
        # The interactive hand page reloads on this, to show the play slides.
        send_timestamped_event(
            channel=hand.event_table_html_channel,
            event_type=SSEEventTypes.TABLE,
            data=data,
        )
