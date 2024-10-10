# an "API" bot

## Why

### Work around bad caching

The current bot is a Django "management" command -- that means it has direct access to the database, and can skip wrapper functions -- e.g., in many of my models, I've overridden the manager class to enforce constraints, but there's no guarantee that, when I wrote the bot code, I remembered to call those wrappers.

In particular, I've got this bad caching setup whereby the bot gets model instances, and then makes DB chanages that *ought to* affect those instances, but due to my caching, the instances become stale until I delete some cached attribute, or entirely refetch the instance.

However, if the bot were written to use a public API, that will isolate it from Django; it will instead just GET and POST JSON objects.

### Only reasonable way to let strangers interact with the system

The current bot cheats as hard as it can, by examining all four hands at a given table before deciding what to do.  That's amusing, but of course if I want strangers to write bots to play bridge, those bots must "see" only what a real player would see -- namely, their own cards, and the dummy, and not much else.  By putting the bot "outside" of the Django app, the app is in complete control of what the bot will see.

## Unsolved Mysteries

- Seems awfully slow!  I've got the bot driving the usual 15 tables at once, and it only gets to a given table every couple of seconds :-|

  Maybe have postgresql log *all* queries to stdout, so I can see if maybe my ORM usage is crazy again.

  Take a look at `a-lot-to-unpack-here` -- that shows me creating a new board.  It's instantiating every existing board for some reason.  Definitely an N^2 problem (i.e., creating N new boards will take N^2 time).

## Solved Mysteries

- How will the bot find out it's its turn to call or play, without periodically fetching the state of the hand?

    I wonder if it can use "long polling" or something -- it requests the hand status, but the server delays the response until it's time for the bot to do its thing.  If the server were an ordinary synchronous server, I'd worry that this would tie up a thread; but since I'm already using daphne (which is async), this seems like it should be cheap.

    Solution: I've already got SSE set up; I just use the SSEClient.
