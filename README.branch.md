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
