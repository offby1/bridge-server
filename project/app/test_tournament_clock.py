"""Tests for the tournament clock: applying deadlines, and working out when to wake.

The clock replaced a `request_finished` receiver throttled to once a minute. Two things
that arrangement never had to answer, and this one does: what happens when two clocks
run at once, and how long should it sleep.
"""

import datetime

import pytest
import time_machine
from django.utils import timezone

from app.models import Hand, Tournament
from app.models.tournament import (
    WAKE_AT_LEAST_EVERY,
    WAY_DISTANT_PLAY_COMPLETION_DEADLINE,
    advance_expired_tournaments,
)


@pytest.mark.django_db
def test_a_passed_signup_deadline_creates_hands(nobody_seated: None) -> None:
    tour = Tournament.objects.get()
    assert not tour.hands().exists()

    with time_machine.travel(tour.signup_deadline + datetime.timedelta(seconds=1), tick=False):
        advance_expired_tournaments()

    assert tour.hands().exists()


@pytest.mark.django_db
def test_running_twice_creates_one_set_of_hands(nobody_seated: None) -> None:
    """Idempotence is what lets us skip a lock.

    Sequential runs are the easy half -- two clocks interleaved is the case the
    database has to settle -- but if this fails, nothing else is worth checking.
    """
    tour = Tournament.objects.get()

    with time_machine.travel(tour.signup_deadline + datetime.timedelta(seconds=1), tick=False):
        advance_expired_tournaments()
        hands_after_one_run = set(Hand.objects.values_list("pk", flat=True))
        advance_expired_tournaments()

    assert set(Hand.objects.values_list("pk", flat=True)) == hands_after_one_run


@pytest.mark.django_db
def test_a_passed_play_deadline_completes_the_tournament(nobody_seated: None) -> None:
    tour = Tournament.objects.get()

    with time_machine.travel(tour.signup_deadline + datetime.timedelta(seconds=1), tick=False):
        advance_expired_tournaments()

    tour.refresh_from_db()
    assert tour.completed_at is None

    with time_machine.travel(
        tour.play_completion_deadline + datetime.timedelta(seconds=1), tick=False
    ):
        advance_expired_tournaments()

    tour.refresh_from_db()
    assert tour.completed_at == tour.play_completion_deadline


@pytest.mark.django_db
def test_completing_twice_keeps_the_first_answer(nobody_seated: None) -> None:
    """The conditional UPDATE is the claim; a second caller must match zero rows."""
    tour = Tournament.objects.get()

    with time_machine.travel(tour.signup_deadline + datetime.timedelta(seconds=1), tick=False):
        advance_expired_tournaments()
    tour.refresh_from_db()

    with time_machine.travel(
        tour.play_completion_deadline + datetime.timedelta(seconds=1), tick=False
    ):
        advance_expired_tournaments()
        tour.refresh_from_db()
        first_answer = tour.completed_at

        advance_expired_tournaments()

    tour.refresh_from_db()
    assert tour.completed_at == first_answer


@pytest.mark.django_db
def test_we_wake_for_a_deadline_sooner_than_the_ceiling(nobody_seated: None) -> None:
    tour = Tournament.objects.get()
    soon = timezone.now() + WAKE_AT_LEAST_EVERY / 2
    # .update() rather than .save(): we're moving a deadline, not signing anybody up.
    Tournament.objects.filter(pk=tour.pk).update(signup_deadline=soon)

    assert advance_expired_tournaments() == soon


@pytest.mark.django_db
def test_we_wake_at_the_ceiling_for_a_deadline_beyond_it(nobody_seated: None) -> None:
    """Sleeping the full five minutes to this fixture's deadline would be wrong.

    Something created in the meantime should not have to wait for it.
    """
    tour = Tournament.objects.get()
    now = timezone.now()
    assert tour.signup_deadline > now + WAKE_AT_LEAST_EVERY

    with time_machine.travel(now, tick=False):
        assert advance_expired_tournaments() == now + WAKE_AT_LEAST_EVERY


@pytest.mark.django_db
def test_we_wake_anyway_when_nothing_is_pending(db: None) -> None:
    """Otherwise a tournament created while we slept would wait for the next request.

    Which is the failure the clock exists to remove.
    """
    assert not Tournament.objects.exists()
    now = timezone.now()

    with time_machine.travel(now, tick=False):
        assert advance_expired_tournaments() == now + WAKE_AT_LEAST_EVERY


@pytest.mark.django_db
def test_the_sentinel_deadline_is_not_something_to_wake_for(nobody_seated: None) -> None:
    """A tournament whose movement isn't known yet carries a deadline a billion years out.

    Sleeping until then would be a bug; sleeping until its *signup* deadline is right.

    Put the tournament into that state explicitly. The fixture's own tournament expires
    in 2999, which is far away but is a real answer, whereas the sentinel means "we
    can't know this yet" and has to be skipped.
    """
    Tournament.objects.update(play_completion_deadline=WAY_DISTANT_PLAY_COMPLETION_DEADLINE)

    assert advance_expired_tournaments() < WAY_DISTANT_PLAY_COMPLETION_DEADLINE
