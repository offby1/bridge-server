# What's all this, then?

See also the `subsume-seat-into-table` branch.

The schema on the `main` branch is subtly wrong; this is better:

* Boards remain the same
* a Hand is
  - exactly one Board
  - exactly four players, each associated with a compass direction
    - maybe a unique constraint on the board and players -- surely four players must not play a given board more than once
  - associated Calls and Plays (the same as what's on main)
  - a table display number ("where" it was played).
    - some unique constraint, presumably in the Tournament model, ensures that one tournament has no more than one table with a given display number
  - whatever other minor fields are already present on main
* There is no longer any such thing as Table -- this is new
* There is no longer any such thing as Seat -- this is new

This branch is the first step towards that.  It looks like it's gonna be a *lot* of work to do, though :-|
