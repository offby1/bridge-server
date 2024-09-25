So I still have a buncha N+1 queries.

In particular, [sentry][1] tells me that fetching `/table/{table_pk}/four-hands` took 1000 ms (admittedly that's an outlier) and did dozens of similar queries; the Django Debug toolbar says `/table/{table_pk}/` did 192 queries in 200 ms (on my laptop, which is awfully fast).

I haven't nailed this down, but I suspect
- I'm simply doing a separate query for each call and play;
- The fix is to gather calls and plays in one or two big queries at the start of the view function, and somehow ensure that the lower-level context-generating and rendering stuff doesn't repeat them. `select_related` and `prefectch_related` might come in handy.
  (Sentry shows that about 75% of the time is spent before rendering, which presumably is context generation.)

** Another idea: use `cached_property` more aggressively.  I recall trying that earlier, and noticing that some such uses broke unit tests, so I backed them out.  But I didn't closely study the breakage; instead I assumed those particular sematics of caching were a bad idea.  But I now think that it might just be that the tests are unrealistic -- I think they fetch a single table, then make all sorts of changes to the associated hand, and examine the table after each change.  That's fine for a test, but our views don't work that way: instead, they fetch a single table, but then they make *at most one* change to the relevant hand.  So I might just need to "refresh" the table in those tests, with something like `t = Table.objects.get(pk=t)` (or some equivalent shortcut, if Django provides one).

I believe the above will work.

Regardless, I notice that I've been using `@property` *a lot* in the models; basically, for any model method that takes no arguments beyond "self".  But I bet many of these methods do a fair bit of computation, and so making them properties is misleading -- when I'm writing code that calls them, I unconsciously assume that since `foo.bar` doesn't have `()` at the end, it must be cheap!  I should at least not use `@property` for methods that are expensive.

::

Tediously tracing through the calls (breadth-first).  I'm ultimately only interested in which calls get made to model methods, since those are the ones that induce SQL queries.

- `/table/{table_pk}/four-hands` : `four_hands_partial_view`
  - calls `_four_hands_context_for_table`
    - calls `table.display_skeleton`
      - calls `self.current_action.xscript`
      - calls `xscript.auction.found_contract`
      - calls `xscript.next_player().seat`
      - calls `self.current_cards_by_seat`
      - calls `xscript.legal_cards()` rather a lot
    - calls `_display_and_control`
      - calls `table.dummy`
      - calls `table.dummy.libraryThing`
      - calls `table.current_action` and `table.current_action.current_trick`
      - calls `table.current_action.player_who_may_play` and `table.current_action.player_who_may_play.seat.direction`
      - calls `as_viewed_by.seat.direction`
      - calls `table.declarer` and `table.declarer.libraryThing`
    - calls `_single_hand_as_four_divs`
      - 🤷
    - calls `_get_pokey_buttons`
      - 🤷
    - calls `_three_by_three_trick_display_context_for_table`
      - calls `h.current_trick`
      - 🤷
--------------------------------------------------------------------------------
  - renders `"four-hands-3x3-partial.html#four-hands-3x3-partial"`
    - calls `table.hand_is_complete`
    - includes `"three-by-three-trick-display-partial.html#three-by-three-trick-display"`

::

Well, tracing (above) seems a waste of time; nothing leaps out at me.

cProfile tells me that my unit test suite invoked something called `query.py:312(query)`, which is presumably deep in django's ORM mojo, *fifty thousand times*.  That seems like a lot!


On the main branch (1a761c0be12aa830fcda65996b808e3715e77d1e), in the shell, with a few tables in various states, all of these do just one query:

```python
t = Table.objects.get(pk=23)
t.current_hand
Hand.objects.get(pk=23)
plays = t.current_hand.play_set.all()
p = plays.first()
plays.all()
Play.objects.all()
Play.objects.first()
```

Since I see lots of queries like `SELECT "app_call"."id", "app_call"."hand_id", "app_call"."serialized" FROM "app_call" WHERE "app_call"."hand_id" = %s ORDER BY "app_call"."id" ASC (23,)`, I put a `pdb.set_trace` call in the query logger, and found that those are coming from `annotated_calls` ... not surprisingly.


[1]: https://eric-hanchrow.sentry.io/performance/trace/aac9e12f08b94151908e45c27c7dfe41/?colorCoding=by+system+vs+application+frame&fov=0%2C1030.0002098083496&node=span-bf91bdad088f8b7f&node=txn-dde1372d1f9a4b35bf221f02aa500e0e&query=&sorting=call+order&statsPeriod=14d&tid=278112709053776&timestamp=1727145274.038647&view=top+down
