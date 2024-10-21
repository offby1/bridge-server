# Wassup homies

## To reproduce it

* `just restore < backup.sql`
* go to <https://erics-work-macbook-pro.tail571dc2.ts.net/>
* log in as diane
* go to <https://erics-work-macbook-pro.tail571dc2.ts.net/hand/97/>
* turn on "god mode" if it isn't already
* click one of kelly's cards

  That gets a 403 with the body

      Hand 99 says: Hey! diane (bot-powered) can't play now; only kelly (bot-powered) can; h.open_access=False

* Perhaps unrelated: <https://erics-work-macbook-pro.tail571dc2.ts.net/api/players/119/> gets an assertion failure

  `The field 'table' was declared on serializer PlayerSerializer, but has not been included in the 'fields' option.`

## Questions to ponder:

* Why are the errors mentioning hand 99 when I asked for hand 97?

  Probably because hand 97 is no longer current, and hand 99 is:

  ```python
  def play_post_view(request: AuthedHttpRequest, seat_pk: str) -> HttpResponse:
    ...
    h = seat.table.current_hand
  ```

  This query confirms that:

  ```sql
    SELECT
        APP_TABLE.ID AS TABLE_ID,
        APP_HAND.*
    FROM
        APP_TABLE
        JOIN APP_HAND ON APP_HAND.TABLE_ID = APP_TABLE.ID
    WHERE
        APP_TABLE.ID = 25
    ORDER BY
        APP_HAND.ID DESC
  ```

  That shows that the board/hand we're examining in the browser -- 14/97 -- is not the most current:

  ```
    "table_id"	"id"	"table_id-2"	"board_id"	"open_access"
    25	99	25	16	false
    25	98	25	15	false
    25	97	25	14	true
    ...
  ```

  How tf did this happen?  Maaaaaybe someone clicked "Next Board Plz" on an incomplete hand, and that just went ahead and assigned a new hand to the table?

  This mismatched-ness is reasonably common:

  `In [7]: {h: h.table.current_hand for h in Hand.objects.all() if not h.is_complete}`

  => note that 3/5 of these incomplete hands are not the `current_hand` at their table:

  ```python
  {<Hand: Hand 131: 13 calls; 4 plays>: <Hand: Hand 131: 13 calls; 4 plays>,
   <Hand: Hand 138: 3 calls; 0 plays>: <Hand: Hand 146: 4 calls; 52 plays>,
   <Hand: Hand 161: 3 calls; 0 plays>: <Hand: Hand 162: 19 calls; 52 plays>,
   <Hand: Hand 154: 13 calls; 2 plays>: <Hand: Hand 154: 13 calls; 2 plays>,
   <Hand: Hand 97: 7 calls; 0 plays>: <Hand: Hand 99: 4 calls; 52 plays>}
  ```

* Why the 403?

  Probably because that response is appropriate for hand 99.

* Why does it say `h.open_access=False` when the browser shows "god mode" is on, and is displaying all four hands?

  Again, probably because that accurately describes hand 99.

* Why do the "hx-post" attributes of all the buttons say "/play/94/"?  I'd think they'd say "/play/97/", wouldn't you?

  Wayul, apparently that 94 is a *seat* ID, not a *hand* ID.  This is confusing, but not, strictly speaking, a bug.

* Why do I see

        2024-10-20T22:06:50+0000 DEBUG hand.py(246) add_play_from_player      diane, sitting South's cards are ♣5♣8♣T♣J♦7♦T♦Q♥3♠3♠6♠9♠T♠K

   in the web server's console output, whereas [the relevant board](https://erics-work-macbook-pro.tail571dc2.ts.net/api/boards/14/) correctly shows `"south_cards": "♣8♣T♣J♣Q♣K♦4♦5♦J♥5♥6♥K♠7♠8"`?  (NB -- the first set of cards would be correct for board 16, which is affiliated with hand 99)

   Probably because `Player.libraryThing` refers to `self.most_recent_seat()`

   I'm starting to think that I should hunt down and kill *most* (not all) uses of methods whose names begin with `most_recent` or `current_`.

## Possily-unrelated questions

In the server output (and correspondingly, in the browser's console), I see frequent errors to the effect of

    2024-10-20T16:18:29+0000 WARNING runserver.py(178) log_action HTTP GET /events/hand/97/ 400 [0.05, 127.0.0.1:51947]
## Solution
I think the problem was that `Player.libraryThing` always used the cards from `self.most_recent_seat.table.current_board`, whereas we were (somehow) looking at a hand that was *not* the most-recently played one.  (How that happened, I dunno.)

So the solution was to pass a Hand object to that method, to make explicit the Hand (and hence Board) we want.

### Prevent this in the future
Couple of ideas about incomplete hands not being a table's most-current:
* prevent it entirely.  Hack `Table.next_board`, and anything similar, to simply refuse to abandon a hand in progress.
* allow it, but mark the abandoned hand as "abandoned", and then ... I dunno ... have the "details" page redirect to the "archive" page; have the "archive" page clearly indicate that it's been abandoned, or something
