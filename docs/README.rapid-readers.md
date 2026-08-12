# Reads live in `app/readers.py`

**Status: this work is finished and merged to `main`.** It was done on a branch called
`rapid-rewrite`; the merge commit is `7ec9b374`. What follows describes the arrangement as
it stands today, plus the reasoning and the traps, so that new reads land in the right
place.

## The general idea

The models were fat. `app/models/hand.py` was around 2000 lines, and a good
share of that was query logic -- code that computes something for a caller to look
at and has no side effects. Mixed in with the write paths, it was hard to find,
hard to test on its own, and it tempted templates into calling model methods that
run queries at render time. (`hand.py` is now about 1000 lines.)

Following [Django RAPID](https://www.django-rapid-architecture.org/), that query
logic now lives in one module, `project/app/readers.py`, as plain
functions that take model instances and return data.

The one rule that matters: **dependencies point one way. Readers import from
models; models never import from readers.** Views, the bot API, `app/broadcast.py`,
management commands and tests all call readers directly.

This moved reads only. Writers, services, and the other RAPID layers were **not**
extracted; those remain separate work, not yet done.

## Where the design came from

`reference/listen-notify-and-rapid-rewrite` carries a full blueprint `readers.py`,
written against an older `main`:

```
git show reference/listen-notify-and-rapid-rewrite:project/app/readers.py
```

We took names and structure from it and adapted the bodies. We did
not merge that branch; it also contains a LISTEN/NOTIFY rework that `main` has
since redone independently (see `docs/README.listen-notify.md`).

## The pattern, per reader

1. Move the logic into `readers.py` as a function taking the model instance (or
   instances) it needs.
2. Delete it from the model or the view.
3. Repoint every caller. Grep for the name -- do not trust line numbers from an
   earlier pass, they shift.
4. For a read a **template** used to call, do not leave a delegating method on the
   model. Have the view compute the value and pass it in the context, and change
   the template to read the context variable. Otherwise the template still
   triggers queries at render time and we have gained nothing.
5. Keep every commit green: `just mypy` and `just ft` both pass before committing,
   one reader (or one small related group) per commit.

Callers say `import app.readers` and then `app.readers.get_whatever(...)`, which
is what the existing call sites in `views/board.py`, `views/feeds.py` and
`views/hand.py` do.

Two things that bit us, recorded so they don't bite again:

- Pre-commit's ruff often prunes an import that the extraction just made unused,
  and that aborts the commit. Re-`git add` the file and commit again.
- Several of these helpers were untyped where they sat. Annotating a reader's
  parameters can surface a genuine `None` that mypy had been letting through. Fix
  it at the call site rather than widening the reader's types.

## What landed

Eleven green commits, oldest first (`just mypy` and `just ft` passed at each one):

| Commit | Reader(s) | Moved from |
|---|---|---|
| `8d4e4144` | `DisplaySkeleton` / `AllFourSuitHoldings` / `SuitHolding` dataclasses, `get_display_skeleton` | `views/hand.py` |
| `58a427d5` | `get_annotated_tricks` | `views/hand.py` |
| `4f229965` | `get_hand_summary`, `get_board_archive_hands` | `Hand` / board archive view |
| `2c7da54a` | `get_hint_for_player` | inline in `hint_view` |
| `d6c0b0b0` | `get_player_summary_by_name_or_pk` | inline in `by_name_or_pk_view` |
| `cf23435e` | `get_chat_disabled_explanation` | `_chat_disabled_explanation`, `views/player.py` |
| `7f1456a0` | `get_player_direction_at_hand`, `player_has_played_hand` | `Player.direction_at_hand`, `Player.has_played_hand` |
| `654cf064` | `get_xscript_updates` | inline in `hand_xscript_updates_view` |
| `836f5494` | `get_hand_status_string` | `Hand.status_string` |
| `508cbda1` | `get_trick_counts_string` | `Hand.trick_counts_string` |
| `9d1d28f9` | `get_auction_display_with_explanations` | `Hand.auction_display_with_explanations` |

(Hashes refer to the branch's history as merged; the subject lines are the reliable
handle.)

Every reader in the blueprint landed, so the extraction is finished. The last three each
needed more than a move, and what they needed is worth remembering:

- **`get_hand_status_string`**. The one caller was a django-tables2 column
  accessor, `tables.A("status_string")`. An accessor names an attribute on the
  record, so it cannot call a reader. The column now declares `empty_values=()`
  and renders itself in `render_status`, which is what the neighbouring `result`
  column already did. django-tables2 calls the render method when the accessor
  fails to resolve, as long as nothing counts as an empty value.
- **`get_trick_counts_string`**. `broadcast.py` calls the reader directly.
  `interactive_hand.html` used to call the model method, so `_interactive_view`
  computes the value and passes `trick_counts_string` in the context.
- **`get_auction_display_with_explanations`**. `auction.html` used to call the
  model method. Every path that renders that template builds its context through
  `_auction_context_for_hand` -- the two direct renders, plus the two templates
  that `{% include %}` it and hand their own context down -- so that funnel is the
  single place that supplies `auction_rows`.

One thing that makes the template moves safer than they look: `django-fastdev`
raises `FastDevVariableDoesNotExist` on a context variable that isn't there, so a
misspelled or missing variable fails loudly instead of rendering an empty string.
Any test that renders the template at all will catch it.

Extracting the auction reader also turned up `auction_partial_view`, which had
been raising `TemplateDoesNotExist` since October 2024 because its template was
folded into `table_detail.html`. Nothing referenced the view, so we deleted it
along with its URL route.

### Deliberately staying put

- `Player.hands_played` and `Player.hand_at_which_we_played_board`: the models
  call these internally, so they are not view-facing reads.
- `Player.current_direction` and `Player.current_hand_and_direction`: the models
  call both of these internally (`dealt_cards` and `current_hand_and_direction`
  itself), so moving them would leave a delegating method behind. They do also
  have callers outside the models -- `views/hand.py` and
  `get_chat_disabled_explanation` -- so we may revisit them; we are leaving them
  alone for now.

### Testing

`app/test_readers.py` calls the readers straight, with no request and no test
client -- which is the payoff of the extraction. It covers what the view tests
never reached rather than re-testing everything: `get_hint_for_player` and
`get_xscript_updates` had no coverage at all before it, because `hint_view` and
`hand_xscript_updates_view` still have no tests and did not before this work either.
`test_table_view.py` also calls `get_display_skeleton` directly.

`just cover` reported **96% coverage of `readers.py`** when this work landed, up from
75% before those tests. What remained uncovered:

- The arithmetic in `get_board_archive_hands` for a numeric score; every hand it
  sees under test scores `"-"`.
- A few branches needing a state we could not readily build, notably a settled
  auction whose final score is 0.

(`AllFourSuitHoldings.from_suit` was uncovered too. It came over from the
blueprint, nothing called it, and we deleted it rather than test it.)

Three traps we hit writing those tests, worth knowing before you write more:

- `play_out_hand` picks the first legal call, which is Pass, so on its own it
  passes the auction out and leaves a hand that is complete with **no tricks**.
  Settle a contract with `set_auction_to` first if you want tricks.
- The `usual_setup` fixture deals each player one whole suit, so every trick is
  four different suits and nobody ever follows suit. Anything about following
  suit needs a normally-dealt hand, which `create_a_tournament` gives you.
- Coverage says nothing about templates: `just test` warns that the Django
  template coverage plugin disabled itself, because template debugging is off in
  the test settings.

Writing those tests turned up a real bug, which we then fixed:
during play, `get_hint_for_player` told *anyone* at the table what the player on
turn should play. It asked whether anybody controlled the seat on turn, and
`player_who_controls_seat` raises rather than returning None, so the check could
never fail. A defender could ask for a hint and be told declarer's card.
`hint_view` behaved the same way before the extraction, so the bug predated this
work; the reader now checks that the controller of that seat is the player who
asked. Declarer still gets hints for dummy's seat, since declarer plays dummy's
cards.
