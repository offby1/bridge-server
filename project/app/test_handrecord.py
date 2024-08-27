from .models import HandRecord, Table


def test_watever(usual_setup):
    t = Table.objects.first()

    h = HandRecord.objects.create(table=t)
    h.call_set.create(serialized="Pass")
    h.call_set.create(serialized="1NT")
    h.call_set.create(serialized="Double")

    assert t.handrecords.count() == 1  # we've only played one hand at this table

    the_hand_record = t.handrecords.first()

    calls = the_hand_record.calls.all()

    assert "means Pass" in str(calls[0])
    assert "means one notrump" in str(calls[1])
    assert "means Double" in str(calls[2])
