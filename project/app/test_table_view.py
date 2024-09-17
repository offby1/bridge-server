import bridge.card

from .models import Table


def test_table_dataclass_thingy(usual_setup):
    t = Table.objects.first()
    ds = t.display_skeleton()
    for dir_ in bridge.card.Suit:
        assert ds[dir_].textual_summary == "13 cards"
