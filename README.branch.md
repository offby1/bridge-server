# Today's bug

https://erics-work-macbook-pro.tail571dc2.ts.net/hand/1/archive/

shows

    Board #1, Neither side vulnerable, dealt by NORTH
    one Club played by amber, sitting East

But then, `52:Declarer! amy (bot) (WEST):`

and the hand record shows

| Trick | Lead |
|-------|------|
| 1 E   | ♥3   |

even though the ♥3 is in South's hand, not East's :-|

```py
In [..]: h1 = Hand.objects.first()
In [11]: pp((h1.get_xscript().tricks))
SELECT COUNT(*) AS "__count"
  FROM "app_call"
 WHERE "app_call"."hand_id" = 1

Execution time: 0.002121s [Database: default]
SELECT COUNT(*) AS "__count"
  FROM "app_play"
 WHERE "app_play"."hand_id" = 1

Execution time: 0.000567s [Database: default]
[<Trick South(3) ➙ ♥3, West(4) ➙ ♥2, North(1) ➙ ♥Q, East(2) ➙ ♥5>,
...
```

OK, so that looks reasonable.  Now:
```py
In [..]: from app.views.hand import _annotate_tricks
In [..]: pp(list(_annotate_tricks(h1.get_xscript())))
[{'number': 1,
  'plays': [{'card': ♥3, 'wins_the_trick': False},
            {'card': <Rank.TWO: 2>, 'wins_the_trick': False},
            {'card': <Rank.QUEEN: 12>, 'wins_the_trick': True},
            {'card': <Rank.FIVE: 5>, 'wins_the_trick': False}],
  'seat': 'E'},
```

D'oh.  It says `'seat': 'E'` when it should say `'seat': 'S'`.
