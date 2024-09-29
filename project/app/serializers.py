from rest_framework import serializers  # type: ignore

from app.models import Board, Hand, Player, Seat, Table


class BoardSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Board
        fields = (
            "east_cards",
            "ew_vulnerable",
            "north_cards",
            "ns_vulnerable",
            "pk",
            "south_cards",
            "west_cards",
        )


class HandSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Hand
        fields = ("table", "board", "pk")


class PlayerSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Player
        fields = ("name", "pk")


class SeatSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Seat
        fields = ("direction", "player", "table", "pk")


class TableSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Table
        fields = ("seat_set", "pk")
