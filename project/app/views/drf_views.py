from __future__ import annotations

import logging

from django.http import HttpResponseNotFound
from rest_framework import permissions, viewsets  # type: ignore
from rest_framework.response import Response  # type: ignore

from app.models import Board, Call, Hand, Play, Player, Seat, Table
from app.serializers import (
    BoardSerializer,
    CallSerializer,
    HandSerializer,
    PlayerSerializer,
    PlaySerializer,
    SeatSerializer,
    TableSerializer,
)
from app.views.table.details import _display_and_control

logger = logging.getLogger(__name__)


def find_table_seat_from_board_and_player(b: Board, player: Player) -> Table | None:
    players_seats = player.seat_set.all()
    boards_hands = b.hand_set.all()
    table_ids_from_seats = players_seats.values_list("table_id", flat=True)
    table_ids_from_boards = boards_hands.values_list("table_id", flat=True)
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

    def retrieve(self, request, pk=None):
        as_viewed_by = request.user.player
        as_dealt = False

        the_board = self.queryset.first()
        if the_board is None:
            return HttpResponseNotFound()
        table = find_table_seat_from_board_and_player(the_board, as_viewed_by)

        rv = {}
        for seat in table.seat_set.all():
            display_and_control = _display_and_control(
                seat=seat.libraryThing, table=table, as_viewed_by=as_viewed_by, as_dealt=as_dealt
            )
            seat_name = seat.libraryThing.name.lower()
            attribute = f"{seat_name}_cards"

            if display_and_control["display_cards"]:
                rv[attribute] = getattr(the_board, attribute)

        return Response(data=rv)


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
