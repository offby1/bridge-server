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


class NoUpdateViewSet(viewsets.ModelViewSet):
    def update(self, request, *args, **kwargs):
        name = getattr(getattr(getattr(self, "queryset", {}), "model", {}), "__name__", "?")
        return Response(f"{name} objects are read-only", status=status.HTTP_403_FORBIDDEN)


class BoardViewSet(NoUpdateViewSet):
    queryset = Board.objects.all()
    serializer_class = BoardSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def _censored_data_dict(self, as_viewed_by: Player | None, board: Board) -> dict[str, str]:
        data_dict = {
            attr: getattr(board, attr)
            for attr in ("ns_vulnerable", "ew_vulnerable", "dealer", "pk")
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

    def list(self, request: AuthedHttpRequest) -> Response:
        censored_objects = []
        for raw_object in self.queryset.order_by("id").all():
            censored_objects.append(
                self._censored_data_dict(as_viewed_by=request.user.player, board=raw_object)
            )

        return Response(data=censored_objects)

    def retrieve(self, request: AuthedHttpRequest, pk=None) -> Response:
        as_viewed_by = request.user.player
        assert as_viewed_by is not None

        try:
            the_board = self.queryset.get(pk=pk)
        except Board.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        return Response(data=self._censored_data_dict(as_viewed_by=as_viewed_by, board=the_board))


class CallViewSet(NoUpdateViewSet):
    queryset = Call.objects.all()
    serializer_class = CallSerializer
    permission_classes = (permissions.IsAuthenticated,)


class HandViewSet(NoUpdateViewSet):
    queryset = Hand.objects.all()
    serializer_class = HandSerializer
    permission_classes = (permissions.IsAuthenticated,)


class PlayViewSet(NoUpdateViewSet):
    queryset = Play.objects.all()
    serializer_class = PlaySerializer
    permission_classes = (permissions.IsAuthenticated,)


# https://www.django-rest-framework.org/api-guide/filtering/#filtering-against-query-parameters
class PlayerViewSet(viewsets.ModelViewSet):
    serializer_class = PlayerSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def update(self, request, *args, **kwargs):
        try:
            target_pk = int(kwargs.get("pk"))
        except ValueError:
            logger.info("Got bogus value for pk: %r", kwargs.get("pk"))
            target_pk = None
        requester_pk = self.request.user.player.pk
        logger.debug(f"{target_pk=} {requester_pk=}")
        if target_pk != requester_pk:
            msg = f"You, {requester_pk=}, may not futz with player {target_pk=}"
            return Response(msg, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Player.objects.all()
        name = self.request.query_params.get("name")
        if name is not None:
            queryset = queryset.filter(user__username=name)
        return queryset


class SeatViewSet(NoUpdateViewSet):
    queryset = Seat.objects.all()
    serializer_class = SeatSerializer
    permission_classes = (permissions.IsAuthenticated,)


class TableViewSet(NoUpdateViewSet):
    queryset = Table.objects.all()
    serializer_class = TableSerializer
    permission_classes = (permissions.IsAuthenticated,)
