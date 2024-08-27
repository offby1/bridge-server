from .models import HandRecord, Table


def test_watever(usual_setup):
    t = Table.objects.first()
    s = t.seat_set.first()
    h = HandRecord.objects.create(seat=s)
    h.call_set.create(serialized="Pass")
    h.call_set.create(serialized="1NT")
    h.call_set.create(serialized="Double")

    assert (
        str(t.handrecord)
        == "So like one dude passed, another said one notrump, then another doubled that shit"
    )
