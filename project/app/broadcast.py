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
import app.models.message
import app.models.player
import app.readers
from app.models.hand import send_timestamped_event
from app.sse_channels import SSEChannels
from app.sse_events import (
    SSEEventTypes,
    create_player_hand_event,
    create_table_event,
)
from bridge.auction import Auction
from bridge.contract import Contract as libContract


def broadcast_after_call(*, hand: app.models.hand.Hand, changed: list[str] | None = None) -> None:
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


def broadcast_after_play(*, hand: app.models.hand.Hand, changed: list[str] | None = None) -> None:
    """Reproduce the SSE fan-out for a card having been played on `hand`.

    Formerly inline in `Hand.add_play_from_model_player`; driven now by the
    app_play INSERT trigger. The just-played card is the most recent row in
    `hand.play_set`, played by the last seat in `hand.annotated_plays`.
    """
    last_play = hand.play_set.order_by("id").last()
    assert last_play is not None

    hand.send_JSON_to_players(
        event_type=SSEEventTypes.BOT_NEW_PLAY,
        data={
            "new-play": {"hand_pk": hand.pk, "serialized": last_play.serialized},
            "tempo_seconds": hand.board.tournament.tempo_seconds,
        },
    )

    send_timestamped_event(
        channel=hand.event_table_html_channel,
        event_type=SSEEventTypes.TABLE,
        data=create_table_event(
            trick_counts_string=app.readers.get_trick_counts_string(hand),
            trick_html=hand._get_current_trick_html(),
        ),
    )

    # When the hand is over, do_end_of_hand_stuff handles the finish and there is
    # no per-seat update to send. Otherwise refresh the seat that just played and
    # the seat now on turn.
    if hand.get_xscript().final_score() is None:
        last_seat = hand.annotated_plays[-1].seat
        hand.send_HTML_update_to_appropriate_channels(last_seat=last_seat)


def broadcast_after_hand_change(
    *, hand: app.models.hand.Hand, changed: list[str] | None = None
) -> None:
    """Reproduce the SSE events for a Hand row's completion or abandonment.

    Driven by the app_hand UPDATE trigger. `changed` is the list of columns whose
    values actually changed, so an ordinary last_action_time save broadcasts
    nothing. Formerly inline in Hand.do_end_of_hand_stuff (the final score) and
    Tournament._finish_play (the play-completion deadline).
    """
    changed = changed or []

    if "is_complete" in changed and hand.is_complete:
        # The auction's caller passed "Passed Out"; a played-out hand passed the
        # score. Reconstruct that here from hand state.
        if hand.auction.status is Auction.PassedOut:
            final_score_text = "Passed Out"
        else:
            final_score_text = str(hand.get_xscript().final_score())
        send_timestamped_event(
            channel=hand.event_table_html_channel,
            event_type=SSEEventTypes.TABLE,
            data=create_table_event(final_score={"text": final_score_text}),
            when=hand.last_action_time.timestamp(),
        )

    # A hand is abandoned either because a tournament's play-completion deadline
    # passed (the tournament is now complete) or because a player walked away
    # mid-hand (the tournament is still running). Only the first case sent a
    # deadline event, so gate on completed_at to tell them apart.
    if (
        "abandoned_because" in changed
        and hand.is_abandoned
        and hand.board.tournament.completed_at is not None
    ):
        deadline = hand.board.tournament.play_completion_deadline
        if deadline is not None:
            app.models.hand.send_event(
                channel=hand.event_table_html_channel,
                event_type=SSEEventTypes.TABLE,
                data=create_table_event(play_completion_deadline=deadline.isoformat()),
            )


def broadcast_player_change(
    *, player: app.models.player.Player, changed: list[str] | None = None
) -> None:
    """Reproduce the SSE fan-out for a player's bot-toggle / seating change.

    Formerly inline in Player._broadcast_changes; driven now by the app_player
    UPDATE trigger, which fires only when allow_bot_to_play_for_me or
    current_hand_id actually changes.
    """
    changed = changed or []
    if "allow_bot_to_play_for_me" not in changed and "current_hand_id" not in changed:
        return

    html = render_to_string(
        "bot-checkbox.html", {"user": SimpleNamespace(player=player), "error_message": None}
    )
    app.models.player.send_event(
        channel=player.bot_checkbox_channel,
        event_type=SSEEventTypes.BOT_CHECKBOX,
        data=html,
        json_encode=False,
    )
    # The bot/API clients learn the setting on their JSON stream.
    app.models.player.send_event(
        channel=player.event_JSON_hand_channel,
        event_type=SSEEventTypes.BOT_SETTING,
        data={"allow_bot_to_play_for_me": player.allow_bot_to_play_for_me},
    )

    # The declarer controls the dummy's hand too, so a declarer's toggle also
    # updates the dummy's (disabled) checkbox.
    if player.current_hand and player.current_hand.model_declarer == player:
        dummy = player.current_hand.model_dummy
        if dummy:
            dummy_html = render_to_string(
                "bot-checkbox.html",
                {"user": SimpleNamespace(player=dummy), "error_message": None},
            )
            app.models.player.send_event(
                channel=dummy.bot_checkbox_channel,
                event_type=SSEEventTypes.BOT_CHECKBOX,
                data=dummy_html,
                json_encode=False,
            )


def broadcast_after_message(*, message: app.models.message.Message) -> None:
    """Reproduce the SSE broadcast for a chat or lobby message.

    Formerly inline in views.lobby.send_lobby_message, views.player.send_player_message,
    and Player._send_partnership_messages; driven now by the app_message INSERT trigger.
    The recipient tells us whether this is a lobby announcement or a private chat.
    """
    recipient = message.recipient_obj
    if isinstance(recipient, app.models.message.Lobby):
        app.models.hand.send_event(
            channel=SSEChannels.LOBBY,
            event_type=SSEEventTypes.LOBBY,
            data=message.as_html(),
        )
    else:
        app.models.hand.send_event(
            channel=app.models.message.Message.channel_name_from_players(
                message.from_player, recipient
            ),
            event_type=SSEEventTypes.CHAT,
            data=message.as_html(),
            json_encode=False,
        )
