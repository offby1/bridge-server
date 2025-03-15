# from https://gist.githubusercontent.com/ChrisTM/5834503/raw/60c19c16a5be2c10c44a8722de965b7ab30dc2cb/throttle.py

from datetime import UTC, datetime, timedelta
from functools import wraps

from django.core.cache import cache


class throttle:
    """Decorator that prevents a function from being called more than once every
    time period.

    To create a function that cannot be called more than once a minute:

        @throttle(minutes=1)
        def my_fun():
            pass

    We store the "time of last call" in django's cache, as opposed to an attribute on our instance, because the former
    is easy to clear at the beginning of every unit test, whereas the latter is not.  And not clearing it before each
    test leads to frustrating flakiness; ask me how I know.

    """

    def __init__(self, seconds=0, minutes=0, hours=0) -> None:
        self.throttle_period = timedelta(
            seconds=seconds,
            minutes=minutes,
            hours=hours,
        )

    def __call__(self, fn):
        def key() -> str:
            return f"throttle:{fn.__qualname__}"

        def get_or_set_time_of_last_call(update: datetime | None = None) -> datetime:
            if update is None:
                return cache.get(key(), default=datetime.min.replace(tzinfo=UTC))
            cache.set(key(), update)
            return update

        @wraps(fn)
        def wrapper(*args, **kwargs):
            now = datetime.now(tz=UTC)
            duration_since_last_call = now - get_or_set_time_of_last_call()

            if duration_since_last_call > self.throttle_period:
                get_or_set_time_of_last_call(now)
                return fn(*args, **kwargs)
            return None

        return wrapper
