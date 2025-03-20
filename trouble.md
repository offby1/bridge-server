# So much trouble

## abandoned hands
After "just drop follow", then "just stress --tiny", <http://localhost:9000/hand/> shows half the hands are abandoned, and the e/w players haven't moved.

```table
| Status | Tournament # | Table | Board | players                            | Result                                                                    |
|--------+--------------+-------+-------+------------------------------------+---------------------------------------------------------------------------|
| good   |            1 |     1 |     1 | _prez, _randy, _rhonda, _marla     | one Heart played by _randy, sitting East: Down 2                          |
| X      |            1 |     1 |     2 | _prez, _randy, _rhonda, _marla     | Auction incomplete                                                        |
| good   |            1 |     2 |     1 | _bodie, _tony gray, _kima, _sydnor | one Club played by _sydnor, sitting West: Made contract with 1 overtricks |
| X      |            1 |     2 |     2 | _bodie, _tony gray, _kima, _sydnor | Auction incomplete                                                        |
```

## looping bots
... also, after the bots have stopped playing, they go into a loop: noticing they're not seated, so exiting and trying again ... over and over.  I'm supposed to *stop* the bots when they're unseated; somehow I've failed to do this.   Or maybe I'm accidentally restarting the bots when I shouldn't.

It feels like I'm trying to reseat players after *one* table has finished, whereas I should wait until *all* tables (in that tournament) have finished.

The one time I paid close attention, I notice the bots started looping *after django restarted*.

- django restarted because I've got docker running with `--watch` and I edited a file.
- `bring_up_all_api_bots` indeed checks to see if the players are seated, and "_kima" e.g. was clearly not seated, and yet ... it brought her up.
- I just rewrote `bring_up_all_api_bots` as `synchronize_bot_states`; let's see if that helps any

I also get the feeling that there's some important event that I'm failing to communicate to the bots -- "tournament round is over", perhaps.

## single player doesn't get to play

So now I've done `just drop follow`, and rather than `just stress`, I signed up & logged in as my old friend bob.  I got a synthetic partner, created a tournament, and skipped the deadline.  And yet ... I see

    Tournament #1
    Movement

    | table | round 1                                              |
    |-------+------------------------------------------------------|
    |     1 | bob, _prez/The Fabulous Phantoms plays board group A |

    Running until March 20, 2025, 8:15 a.m. PDT.

I.e., rather than create synthetic opponents, I got phantoms :-|

I suspect I should *never* allow phantoms, and instead *always* create synths.

## overall unmanageable complexity
OK this is getting too complex!  Maybe I should

* add a method to the "movement" class that's basically "gimme boards and players for round 3, table 2", and test that; then it should be easy to invoke it from the django-y stuff

* remove all references to models in movements.py.  That'd bring it back to how it was when I first was thinking about it, and would make it easier to test.
