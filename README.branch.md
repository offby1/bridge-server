# Reproduce, understand, fix the bug I hit at 2024-10-07 03:32:16,975

Log is `log.txt`; a db snapshot taken soon after is `buggy-postgres-dump`.

## the unique constraint violation is a bit older than I thought

It repros at this commit (and no earlier)

    3a72fc4ac8d5cb1ef7bbb12b33814c7314d9bcac
    Author:     Eric Hanchrow <eric.hanchrow@gmail.com>
    AuthorDate: 2024-10-03 16:29:24 -0700

    Merge branch 'slightly-smarter-bot'

To get it to repro, run `just drop pop`.

Thoughts:

## Why do I have that assertion at models/table.py line 207?

I think because I assume that every table must have a hand associated with it.  `TableManager.create_with_two_partnerships` clearly *aims* to enforce that constraint, although I suspect it can fail; e.g. I have indeed seen its call to `Hand.objects.create(board=b, table=t)` fail with a uniqueness violation; it looks like, when that happens, the bogus handless table hangs around.

I guess it's possible that there was a race in `TableManager.create_with_two_partnerships` although it seems unlikely, and I can't think of how I could confirm or deny that.  But anyway, here's what the race would look like:

- Two threads are running that method more or less at once.
- Thread one gets allocated table one.
- Thread two gets allocated table two.
- Thread one associates table one with board one.
- Thread two attempts to associate table two with board one, and gets a uniqueness violation.
  Thus table two now hangs around, a sort of land mine -- a table with no hand.
- Later someone examines table two via the web, and it go boom.

OTOH, it'd be great if the logs showed a unique violation, later followed by this assertion failure, on a given table; that would confirm this hypothesis.  I see no such thing.  However, I *do* see the uniqe violation for `/table/new/32/1/`; that's a puzzle since we only have 15 tables.  Why were we trying to create table 32? I *think* the IDs for tables go up by one each time.
