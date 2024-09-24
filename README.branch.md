So I still have a buncha N+1 queries.

In particular, [sentry][1] tells me that fetching `/table/{table_pk}/four-hands` took 1000 ms (admittedly that's an outlier) and did dozens of similar queries; the Django Debug toolbar says `/table/{table_pk}/` did 192 queries in 200 ms (on my laptop, which is awfully fast).

I haven't nailed this down, but I suspect
- I'm simply doing a separate query for each call and play;
- The fix is to gather calls and plays in one or two big queries at the start of the view function, and somehow ensure that the lower-level context-generating and rendering stuff doesn't repeat them. `select_related` and `prefectch_related` might come in handy.

[1]: https://eric-hanchrow.sentry.io/performance/trace/aac9e12f08b94151908e45c27c7dfe41/?colorCoding=by+system+vs+application+frame&fov=0%2C1030.0002098083496&node=span-bf91bdad088f8b7f&node=txn-dde1372d1f9a4b35bf221f02aa500e0e&query=&sorting=call+order&statsPeriod=14d&tid=278112709053776&timestamp=1727145274.038647&view=top+down
