from rest_framework import permissions, viewsets

from app.models import Board
from app.serializers import BoardSerializer


class BoardViewSet(viewsets.ModelViewSet):
    queryset = Board.objects.all().order_by("-id")
    serializer_class = BoardSerializer
    permission_classes = [permissions.IsAuthenticated]
