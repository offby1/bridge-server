# What is a "movement"?

## What problem does it solve

It solves the same problem that boards, and duplicate bridge itself, solves: it reduces the role of chance in a pair's final score.

E.g., since any fool can get a high score if they pick up their hand and find they've been dealt all thirteen spades, we smooth things out by giving each pair (well, each pair of pairs) the same cards.  That way, if anyone gets all thirteen spades, then *everyone* will get them, and the score will reflect how well they played them.

So similarly: any fool can get a high score if their opponents are on crack, so we smooth things out by having each pair sit against each other pair.

It also solves the problem: we have N pairs, and some number of boards; we'd like each pair to play the same number of boards, and ideally, as many boards as possible.  I.e., we could satisfy "play the same number of boards" by having everyone just stay home, thereby playing *zero* boards per pair; but that wouldn't serve the ultimate goal of letting pairs see how they do relative to other pairs.

We want to play as many boards as possible, up to some reasonable number -- typically 3 or so per "round", with enough rounds to play each other pair.

This also limits the number of pairs per tournament: if you had 1,000 pairs, you could theoretically have
```py
>>> np = 1000
>>> print(np * (np - 1) / 2)
499500.0
```
pair-to-pair matchups, but nobody wants to play half a million hands; they want to play maybe three hours' worth, which would be, I dunno, 18 or 20 or 24 boards, like that.

## How do we solve it

I'm thinking -- in Python terms, a movement is a callable that takes, as arguments:

* a set of boards
* a set of pairs

and it returns a sequence, each of which is a collection of Tables, each with a board and some pairs.  Each element of the sequence represents a "round".

Some constraints about that sequence:

* Not too many rounds! 20 max, maybe?  (Each round will take something like 10 minutes, and a tournament should last, I dunno, three hours)
* Every pair appears in each element (not possible if we have an odd number of pairs)
* No element has the same board/pair combo as any other element (i.e., players don't see the same board twice)
* The number of distinct pair/table combinations in the sequence is something like 1/3 of the total number of elements in the sequence -- that means that each pair plays three rounds at a table before they or their opponents move
* You *might* want e.g. the N/S pairs to stay put, and the E/W pairs to move -- that's how things work in the Real World, iirc; but given that there's no physical movement involved, it should be fine to have both pairs move.
* It'd be *nice* if each pair could play the boards in order, but ...

Each tournament would have exactly one movement associated with it, at the time the tournament is created.  It cannot change.

<https://en.wikipedia.org/wiki/Duplicate_bridge_movements#Barometer_games_and_online_bridge_movements> suggests that I don't need no fancy movements, but I haven't yet figured out what they're referring to :-|
> In a barometer movement all players play the same boards simultaneously, and all that is required is to rotate the players.

<https://www.bridgewebs.com/crowborough/Pair%20Movements.htm> seems readable.
