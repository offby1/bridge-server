# The `rapid-rewrite` branch: moving reads into `app/readers.py`

## The general idea

The models are fat. `app/models/hand.py` alone is around 2000 lines, and a good
share of that is query logic -- code that computes something for a caller to look
at and has no side effects. Mixed in with the write paths, it is hard to find,
hard to test on its own, and it tempts templates into calling model methods that
run queries at render time.

Following [Django RAPID](https://www.django-rapid-architecture.org/), this branch
collects that query logic into one module, `project/app/readers.py`, as plain
functions that take model instances and return data.

The one rule that matters: **dependencies point one way. Readers import from
models; models never import from readers.** Views, the bot API, management
commands and tests all call readers directly.

This branch moves reads only. We are not extracting writers, services, or any
other RAPID layer here; those are separate work and are **not** part of this
branch.

## Where the design came from

`reference/listen-notify-and-rapid-rewrite` carries a full blueprint `readers.py`,
written against an older `main`:

```
git show reference/listen-notify-and-rapid-rewrite:project/app/readers.py
```

We take names and structure from it and adapt the bodies to current `main`. We do
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

## Status

Everything in this section describes the branch **as it stands today**.

### Landed

Eleven green commits, oldest first (`just mypy` and `just ft` pass at each one):

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

(Hashes refer to this branch's history; a rebase will change them, the subject
lines will not.)

Every reader in the blueprint has now landed, so the extraction this branch set
out to do is finished. The last three each needed more than a move, and what they
needed is worth remembering:

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

### Testing, and what is not covered

There is no `test_readers.py` today, and we deliberately did not write one: the
extraction is meant to preserve behaviour, and the existing view and model tests
are what demonstrate that. `test_table_view.py` is the one place that calls a
reader (`get_display_skeleton`) directly.

`just test` reports **75% coverage of `readers.py`** as of this commit. The gaps
are worth naming, because two readers are not exercised at all:

- **`get_hint_for_player`** and **`get_xscript_updates`** have no coverage. Their
  views, `hint_view` and `hand_xscript_updates_view`, have no tests either -- and
  did not before this branch, when the same logic sat inline in them. So this is a
  pre-existing gap that the extraction neither caused nor closed.
- `get_annotated_tricks` runs, but only ever on hands with no completed trick, so
  its per-trick loop body is uncovered.
- `get_hand_status_string` is only ever reached for one of its three outcomes.
- `get_hand_summary` runs, but several of its branches (the not-yet-played-the-board
  refusal, and the scoring arithmetic once a final score exists) do not.

Direct unit tests would close all of that cheaply, and are the obvious next piece
of work. We have not written them. The point of the extraction is that they are
now easy: each reader is a function over model instances, with no request and no
side effects.

Note also that `just test` prints a warning that the Django template coverage
plugin disabled itself because template debugging is off in the test settings, so
template lines count toward no coverage figure at all.
