from .models import HandRecord, Table


def test_watever(usual_setup):
    t = Table.objects.first()

    h = HandRecord.objects.create(table=t)
    h.call_set.create(serialized="Pass")
    h.call_set.create(serialized="1NT")
    h.call_set.create(serialized="Double")

    assert (
        ", ".join([str(h) for h in t.handrecords.all()])
        == "So like one dude passed, another said one notrump, then another doubled that shit"
    )
