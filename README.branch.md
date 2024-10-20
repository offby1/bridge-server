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

## So:

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

  How tf did this happen?

* Why the 403?

  Probably because that response is appropriate for hand 99.

* Why does it say `h.open_access=False` when the browser shows "god mode" is on, and is displaying all four hands?

  Again, probably because that accurately describes hand 99.

* Why do the "hx-post" attributes of all the buttons say "/play/94/"?  I'd think they'd say "/play/97/", wouldn't you?

  Wayul, apparently that 94 is a *seat* ID, not a *hand* ID.  This is confusing, but not, strictly speaking, a bug.

## Oh and also

In the server output (and correspondingly, in the browser's console), I see frequent errors to the effect of

    2024-10-20T16:18:29+0000 WARNING runserver.py(178) log_action HTTP GET /events/hand/97/ 400 [0.05, 127.0.0.1:51947]
