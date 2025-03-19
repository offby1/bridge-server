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

I also get the feeling that there's some important event that I'm failing to communicate to the bots -- "tournament round is over", perhaps.

## overall unmanageable complexity
OK this is getting too complex!  Maybe I should

* add a method to the "movement" class that's basically "gimme boards and players for round 3, table 2", and test that; then it should be easy to invoke it from the django-y stuff
