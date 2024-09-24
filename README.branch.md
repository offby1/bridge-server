On the main branch, in the shell, with a few tables in various states:

- `t = Table.objects.get(pk=23)`

  Just one obvious query.

- `t.current_hand`

  160(!) queries, many of them UPDATE
  ```
     53 SELECT "app_play"."id",
     52 UPDATE "app_play"
     52 SELECT "app_call"."id",
  ```

  clearly we're walking along each call and each play.

- similarly `Hand.objects.get(pk=23)`

- fetching just a single play is, happily, less painful, but still:
  - we're doing `SELECT FROM app_play` twice
  - we're doing the `UPDATE` every time

In [7]: t.current_hand.play_set.first()
SELECT "app_play"."id",
       "app_play"."won_its_trick",
       "app_play"."hand_id",
       "app_play"."serialized"
  FROM "app_play"
 WHERE "app_play"."hand_id" = 23
 ORDER BY "app_play"."id" ASC
 LIMIT 1

Execution time: 0.001776s [Database: default]
Out[7]: SELECT "app_call"."id",
       "app_call"."hand_id",
       "app_call"."serialized"
  FROM "app_call"
 WHERE "app_call"."hand_id" = 23
 ORDER BY "app_call"."id" ASC

Execution time: 0.000731s [Database: default]
SELECT "app_play"."id",
       "app_play"."won_its_trick",
       "app_play"."hand_id",
       "app_play"."serialized"
  FROM "app_play"
 WHERE "app_play"."hand_id" = 23
 ORDER BY "app_play"."id" ASC

Execution time: 0.000751s [Database: default]
UPDATE "app_play"
   SET "won_its_trick" = true
 WHERE ("app_play"."hand_id" = 23 AND "app_play"."id" = 1008)

Execution time: 0.006488s [Database: default]
<Play: South at Table 23 played ♥A*>
