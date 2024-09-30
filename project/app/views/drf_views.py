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

# from app.views.table.details import _display_and_control


class BoardViewSet(viewsets.ModelViewSet):
    queryset = Board.objects.all()
    serializer_class = BoardSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def retrieve(self, request, pk=None):
        as_viewed_by = request.user
        the_board = self.queryset.first()
        if the_board is None:
            return HttpResponseNotFound()
        print(f"{self.queryset=} {self=} {request=} {as_viewed_by=} {pk=} {the_board=}")
        return Response(data="piss off, you", status=403)


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
