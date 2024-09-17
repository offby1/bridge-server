from bridge.seat import Seat

from .models import Table


def test_table_dataclass_thingy(usual_setup):
    t = Table.objects.first()
    ds = t.display_skeleton()
    for dir_ in Seat:
        assert ds[dir_].textual_summary == "13 cards"
