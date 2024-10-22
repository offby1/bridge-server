logged in as bob
at https://teensy-info.tail571dc2.ts.net/hand/76/
I clicked "1C" from the bidding box (`/call/76/`)
got a 403 that says `bob, sitting South isn't allowed to call now; only        bob, sitting South is`

So the library is comparing "who_clicked" with "whose turn is it to call", and finding that the seats and names are the same, but the hand holdings are different, and failing the comparison because of that:

    AssertionError: Just gonna guess ♣5♣6♣K♦2♦4♦8♥2♥9♥Q♠7♠T♠J♠Q != ♣5♣8♣T♣J♦7♦T♦Q♥3♠3♠6♠9♠T♠K

I will further guess that one of those holdings corresponds to the actual hand we're looking at (#76), and the other to ... uh ... some other hand?

```py
    In [1]: h76 = Hand.objects.get(pk=76)
    In [5]: h76.board.south_cards
    Out[5]: '♣5♣6♣K♦2♦4♦8♥2♥9♥Q♠7♠T♠J♠Q'
```

ka-ching

The other hand is either board #1 or board #16

> boards 1 and 16 are identical! how tf did that happen?!  Maybe I generated boards 1-15 all in one go, then later generated 16 on demand and did `random.seed(0)` both times.

