import logging


from app.models import Board, Hand, Player, Tournament


from app.views.hand import _everything_read_only_view

from app.testutils import play_out_hand

logger = logging.getLogger()


def test_dispatcher() -> None: ...


# I tried to incorporate this test into test_both_important_views above, but it was a mess.
def test_weirdo_special_case(db, rf):
    t1 = Tournament.objects.create()
    b1, _ = Board.objects.get_or_create_from_display_number(
        display_number=1, tournament=t1, group="A"
    )
    North, South, East, West = [Player.objects.create_synthetic() for _ in range(4)]
    North.partner_with(South)
    East.partner_with(West)
    Ding, Dong, Witch, Dead = [Player.objects.create_synthetic() for _ in range(4)]
    Ding.partner_with(Dong)
    Witch.partner_with(Dead)
    h1 = Hand.objects.create(
        board=b1, North=North, East=East, West=West, South=South, table_display_number=1
    )
    h2 = Hand.objects.create(
        board=b1, North=Ding, East=Dong, West=Witch, South=Dead, table_display_number=2
    )
    play_out_hand(h1)

    # North can "see" all of h1.
    request = rf.get("/woteva/", data={"pk": h1.pk})
    setattr(request, "session", {})
    request.user = North.user

    assert _everything_read_only_view(request=request, pk=h1.pk).status_code == 200

    # North can also "see" all of h2, even though it's not complete.
    assert _everything_read_only_view(request=request, pk=h2.pk).status_code == 200
