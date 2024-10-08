Reproduce, understand, fix the bug I hit at 2024-10-07 03:32:16,975

Log is `log.txt`; a db snapshot taken soon after is `buggy-postgres-dump`.

Thoughts:

- Why do I have that assertion at models/table.py line 207?

  I think because I assume that every table must have a hand associated with it.  `TableManager.create_with_two_partnerships` clearly *aims* to enforce that constraint, although I suspect it can fail; e.g. I have indeed seen its call to `Hand.objects.create(board=b, table=t)` fail with a uniqueness violation, and yet I imagine the bogus table hangs around.
