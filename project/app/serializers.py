from rest_framework import serializers  # type: ignore

from app.models import Board


class BoardSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Board
        fields = [
            "east_cards",
            "ew_vulnerable",
            "north_cards",
            "ns_vulnerable",
            "pk",
            "south_cards",
            "west_cards",
        ]
