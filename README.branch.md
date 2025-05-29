# This one's tricky

Looks like

* we create a new tournament based on the signed-up players, and their partnerships.
* we populate the cache with a movement based on the above.
* everything is fine.
* one of the partnerships splits up.
* we delete the cache, and then try to repopulate it.
* Now things go kablooey, because
  * the cache-population thing sees that some hands exist, and assumes that the players it finds in those hands are *still* partnered up as before
  * but gets an exception (something like "None" object has no "pk" attribute) when it turns out they're not

## Ideas for fixing

Easiest first.

- somehow tell Django's cache system to use the database, instead of ... whatever it's currently using (just a chunk of RAM, iirc), so that the cache doesn't vanish when the server restarts.

  This won't fix the existing unit test (which explicitly clears the cache) but so what; we can assume the db is durable.

  This also, alas, won't really make the problem go away in prod, since the cache-population thing still needs to run, and any tournament might have its partnerships dissolved at any time.

- (manually) persist the movement in the db instead of the cache, so that it cannot go away and hence never needs to be recreated.

- smarten up the cache-population thing, in the case that some hands already exist, by ... somehow noting the various partnerships that pertained at the time the signup deadline expired

  Turns out this wasn't hard at all.

- don't purge TournamentSignups when the signup deadline expires; instead ... I dunno ... mark the various players as having been assigned to their tournaments, *and* mark the partnerships.  That way there should be enough information in this model for the cache-population code to do its thing.

  That also sounds messy.
