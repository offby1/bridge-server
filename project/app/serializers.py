from rest_framework import serializers  # type: ignore

from app.models import Board, Call, Hand, Play, Player, Seat, Table


class BoardSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Board
        # TODO -- figure out how to only show those cards that belong to the caller's hand!
        fields = (
            "east_cards",
            "ew_vulnerable",
            "north_cards",
            "ns_vulnerable",
            "pk",
            "south_cards",
            "west_cards",
        )


class CallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Call
        fields = ("serialized",)


class HandSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Hand
        fields = ("pk", "table", "board", "serialized_plays", "serialized_calls")


class PlaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Play
        fields = ("won_its_trick", "serialized")


class PlayerSerializer(serializers.HyperlinkedModelSerializer):
    table = serializers.HyperlinkedRelatedField(view_name="table-detail", read_only=True)

    class Meta:
        model = Player
        fields = ("name", "pk", "allow_bot_to_play_for_me", "table")


class SeatSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Seat
        fields = ("direction", "player", "table", "pk")


class TableSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Table
        fields = ("seat_set", "pk")
