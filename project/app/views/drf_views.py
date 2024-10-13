from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import bridge.seat
from rest_framework import permissions, status, viewsets  # type: ignore
from rest_framework.response import Response  # type: ignore

from app.models import Board, Call, Hand, Play, Player, Seat, Table, logged_queries
from app.serializers import (
    BoardSerializer,
    CallSerializer,
    HandSerializer,
    PlayerSerializer,
    PlaySerializer,
    SeatSerializer,
    TableSerializer,
)
from app.views.hand import _display_and_control

if TYPE_CHECKING:
    from app.views.misc import AuthedHttpRequest

logger = logging.getLogger(__name__)


def find_table_seat_from_board_and_player(b: Board, player: Player) -> Table | None:
    players_seats = player.seat_set.all()
    boards_hands = b.hand_set.all()
    table_ids_from_seats = players_seats.values_list("table_id", flat=True)
    table_ids_from_boards = boards_hands.values_list("table_id", flat=True)
    print(
        f"seats: {[s.pk for s in players_seats]} hands: {[h.pk for h in boards_hands]} {table_ids_from_seats=} {table_ids_from_boards=}"
    )
    # TODO -- maybe assert there is no more than one
    return (
        Table.objects.filter(pk__in=table_ids_from_seats)
        .filter(pk__in=table_ids_from_boards)
        .first()
    )


class BoardViewSet(viewsets.ModelViewSet):
    queryset = Board.objects.all()
    serializer_class = BoardSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def retrieve(self, request: AuthedHttpRequest, pk=None) -> Response:
        print()
        as_viewed_by = request.user.player
        assert as_viewed_by is not None

        the_board = self.queryset.get(pk=pk)

        if the_board is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        data_dict = {
            attr: getattr(the_board, attr) for attr in ("ns_vulnerable", "ew_vulnerable", "dealer")
        }

        with logged_queries():
            hand_at_which_our_viewer_played_this_board = Hand.objects.filter(
                board=the_board,
                table__in=Table.objects.filter(
                    pk__in=as_viewed_by.seat_set.values_list("table_id", flat=True).all()
                ).all(),
            ).first()

        if hand_at_which_our_viewer_played_this_board is not None:
            for seat in bridge.seat.Seat:
                print(f"retrieve examining {hand_at_which_our_viewer_played_this_board.pk=} {seat}")
                print(f"{hand_at_which_our_viewer_played_this_board.is_complete=}")
                display_and_control = _display_and_control(
                    seat=seat,
                    hand=hand_at_which_our_viewer_played_this_board,
                    as_viewed_by=as_viewed_by,
                    as_dealt=hand_at_which_our_viewer_played_this_board.is_complete,
                )
                seat_name = seat.name.lower()
                attribute = f"{seat_name}_cards"

                if display_and_control["display_cards"]:
                    data_dict[attribute] = getattr(the_board, attribute)

        return Response(data=data_dict)


class CallViewSet(viewsets.ModelViewSet):
    queryset = Call.objects.all()
    serializer_class = CallSerializer
    permission_classes = (permissions.IsAuthenticated,)


class HandViewSet(viewsets.ModelViewSet):
    queryset = Hand.objects.all()
    serializer_class = HandSerializer
    permission_classes = (permissions.IsAuthenticated,)


class PlayViewSet(viewsets.ModelViewSet):
    queryset = Play.objects.all()
    serializer_class = PlaySerializer
    permission_classes = (permissions.IsAuthenticated,)


class PlayerViewSet(viewsets.ModelViewSet):
    queryset = Player.objects.all()
    serializer_class = PlayerSerializer
    permission_classes = (permissions.IsAuthenticated,)


class SeatViewSet(viewsets.ModelViewSet):
    queryset = Seat.objects.all()
    serializer_class = SeatSerializer
    permission_classes = (permissions.IsAuthenticated,)


class TableViewSet(viewsets.ModelViewSet):
    queryset = Table.objects.all()
    serializer_class = TableSerializer
    permission_classes = (permissions.IsAuthenticated,)
