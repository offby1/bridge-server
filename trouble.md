# Now what

## Whole lotta flappin' goin' on

i.e., when I did "just follow" and then "just stress", afaict the bots all just exited and tried again

`django-1  | 2025-04-03T00:18:09+0000 DEBUG apibot request_id=7588652631764f8e9e3e29d2d0495a5c (   109) bob       : apibot.py 248 <module> Hm, we don't seem to be seated; let's bail` seems pertinent.

## Somehow the movement code is trying to fetch "phantom" players (those with negative IDs) from the db

I thought I did something somewhere to ensure that we never actually trigger the code in movements.py that creates those
