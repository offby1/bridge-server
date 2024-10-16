from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import bridge.seat
from rest_framework import permissions, status, viewsets  # type: ignore
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
from app.views.hand import _display_and_control

if TYPE_CHECKING:
    from app.views.misc import AuthedHttpRequest

logger = logging.getLogger(__name__)


class BoardViewSet(viewsets.ModelViewSet):
    queryset = Board.objects.all()
    serializer_class = BoardSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def _censored_data_dict(self, as_viewed_by: Player | None, board: Board) -> dict[str, str]:
        data_dict = {
            attr: getattr(board, attr) for attr in ("ns_vulnerable", "ew_vulnerable", "dealer")
        }

        if as_viewed_by is None:
            data_dict["where_are_the_damned_cards"] = f"{as_viewed_by=} so no cards for you"
        else:
            hand = as_viewed_by.hand_at_which_board_was_played(board)

            if hand is not None:
                for seat in bridge.seat.Seat:
                    display_and_control = _display_and_control(
                        seat=seat,
                        hand=hand,
                        as_viewed_by=as_viewed_by,
                        as_dealt=hand.is_complete,
                    )
                    seat_name = seat.name.lower()
                    attribute = f"{seat_name}_cards"

                    if display_and_control["display_cards"]:
                        data_dict[attribute] = getattr(board, attribute)

        return data_dict

    def retrieve(self, request: AuthedHttpRequest, pk=None) -> Response:
        as_viewed_by = request.user.player
        assert as_viewed_by is not None

        try:
            the_board = self.queryset.get(pk=pk)
        except Board.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        return Response(data=self._censored_data_dict(as_viewed_by=as_viewed_by, board=the_board))


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
