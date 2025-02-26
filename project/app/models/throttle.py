# from https://gist.githubusercontent.com/ChrisTM/5834503/raw/60c19c16a5be2c10c44a8722de965b7ab30dc2cb/throttle.py

from datetime import datetime, timedelta, UTC
from functools import wraps


class throttle:
    """Decorator that prevents a function from being called more than once every
    time period.

    To create a function that cannot be called more than once a minute:

        @throttle(minutes=1)
        def my_fun():
            pass
    """

    def __init__(self, seconds=0, minutes=0, hours=0) -> None:
        self.throttle_period = timedelta(
            seconds=seconds,
            minutes=minutes,
            hours=hours,
        )
        self.time_of_last_call = datetime.min.replace(tzinfo=UTC)

    def __call__(self, fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            now = datetime.now(tz=UTC)
            time_since_last_call = now - self.time_of_last_call

            if time_since_last_call > self.throttle_period:
                self.time_of_last_call = now
                return fn(*args, **kwargs)
            return None

        return wrapper
