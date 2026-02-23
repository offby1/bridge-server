From a discussion with Claude:

❯ I notice we're now running migrations with the new code, while the old code is still running.  Isn't there a risk
  that, say, our migration renames a column, but the old code is still using it?  Then there'd be an (admittedly short)
  period of time where we'd get big scary 500 errors.

⏺ Yes, that's a real risk. It's a well-known problem with zero-downtime deploys, and the standard solution is to make
  migrations backwards-compatible — i.e., never rename or delete a column in a single deploy. Instead you'd do it in two
  deploys:

  1. Deploy 1: Add the new column, backfill data, update code to write to both columns but read from the old one
  2. Deploy 2: Switch reads to the new column, stop writing to the old one, drop the old column

  That said — for a bridge card game with a handful of users, this is almost certainly not worth the complexity. The window
  between migrations running and the new container starting is a few seconds at most. If you ever do a column rename, you
  could just accept the brief blip, or do it during a quiet moment.

  The current approach is a good pragmatic tradeoff: you've cut downtime from ~1 minute to a few seconds, and the migration
  risk is theoretical for most changes you'd actually make.
