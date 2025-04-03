# Now what

## Somehow the movement code is trying to fetch "phantom" players (those with negative IDs) from the db

I thought I did something somewhere to ensure that we never actually trigger the code in movements.py that creates those
