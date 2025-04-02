# Now what

## most (all?) request_ids in the logs are "none"

## Whole lotta flappin' goin' on

i.e., when I did "just follow" and then "just stress", afaict the bots all just exited and tried again

## Somehow the movement code is trying to fetch "phantom" players (those with negative IDs) from the db

I thought I did something somewhere to ensure that we never actually trigger the code in movements.py that creates those
