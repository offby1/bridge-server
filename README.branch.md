Testing ideas

In another branch, I tried testing with pytest-django's "live_server" fixture, and playwright; never got it working.

So maybe just a manual test :-|

Using the `nearly_completed_tournament` fixture

- `just fixture nearly_completed_tournament`
- `just runserver`
- log in as I guess Clint, view hand 1
- `just shell` and set the tournament's expiry to now
  - ```t = Tournament.objects.first()
      from django.utils.timezone import now
      t.play_completion_deadline = now()
      t.save()
      from app.models import tournament
      tournament.check_for_expirations.__wrapped__("some manual test")
    ```
- trigger things by opening a new browser window at the home page
- hopefully the "hand 1" page will have reloaded
