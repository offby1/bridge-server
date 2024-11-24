from rest_framework import serializers  # type: ignore [import-untyped]

from app.models import Board, Call, Hand, Play, Player, Seat, Table


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


class CallSerializer(serializers.ModelSerializer):
    seat_pk = serializers.IntegerField(read_only=True)
    hand_id = serializers.IntegerField()

    class Meta:
        model = Call
        fields = ("serialized", "hand_id", "seat_pk")
        depth = 1


class ReadOnlyCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Call
        fields = ("serialized", "hand", "seat_pk")
        depth = 1


class HandSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Hand
        fields = (
            "pk",
            "table",
            "board",
            "is_complete",
            "serializable_xscript",
            "open_access",
        )


class ShallowTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ("seat_set", "id", "current_hand_pk", "tempo_seconds")
        depth = 1


class NewHandSerializer(serializers.ModelSerializer):
    """Yes, I am a lot like HandSerializer.  But:

    - I don't have the serialized_calls or serialized_plays, since I represent a *new* hand, and those would always be
      empty;

    - I don't inherit from HyperlinkedModelSerializer, since that would require that my caller pass in a request, which
      he doesn't have.

    """

    table = ShallowTableSerializer()

    class Meta:
        model = Hand
        fields = ("pk", "table", "board")


# The bot uses this to create plays
class PlaySerializer(serializers.ModelSerializer):
    seat_pk = serializers.IntegerField(read_only=True)
    hand_id = serializers.IntegerField()

    class Meta:
        model = Play
        fields = ("serialized", "hand_id", "seat_pk")


# Anyone can use this to examine a play.  I haven't figured out how to combine the two serializers that does both things.
class ReadOnlyPlaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Play
        fields = ("serialized", "hand", "seat_pk")
        depth = 1


class PlayerSerializer(serializers.HyperlinkedModelSerializer):
    current_table = serializers.HyperlinkedRelatedField(view_name="table-detail", read_only=True)

    class Meta:
        model = Player
        fields = ("name", "pk", "allow_bot_to_play_for_me", "current_table")


class SeatSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Seat
        fields = ("direction", "player", "table", "pk")


class TableSerializer(serializers.HyperlinkedModelSerializer):
    current_hand = serializers.HyperlinkedRelatedField(view_name="hand-detail", read_only=True)

    class Meta:
        model = Table
        fields = ("seat_set", "pk", "current_hand", "tempo_seconds")
