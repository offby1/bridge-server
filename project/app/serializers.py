from rest_framework import serializers  # type: ignore

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


class HandSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Hand
        fields = (
            "pk",
            "table",
            "board",
            "is_complete",
            "serialized_plays",
            "serialized_calls",
            "open_access",
        )


class NewHandSerializer(serializers.ModelSerializer):
    """Yes, I am a lot like HandSerializer.  But:

    - I don't have the serialized_calls or serialized_plays, since I represent a *new* hand, and those would always be
      empty;

    - I don't inherit from HyperlinkedModelSerializer, since that would require that my caller pass in a request, which
      he doesn't have.

    Also:

    - There's no need to make a route for me, since nobody needs to fetch me via a web service call; I am used only to
      serialize a hand to be sent in a django-eventstream event.

    """

    class Meta:
        model = Hand
        fields = ("pk", "table", "board")
        depth = 1


class PlaySerializer(serializers.ModelSerializer):
    seat_pk = serializers.IntegerField(read_only=True)
    hand_id = serializers.IntegerField()

    class Meta:
        model = Play
        fields = ("serialized", "hand_id", "seat_pk")


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
        fields = ("seat_set", "pk", "current_hand")
