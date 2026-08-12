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

Eight green commits, oldest first:

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

(Hashes refer to this branch's history; a rebase will change them, the subject
lines will not.)

### Not yet moved

The blueprint has three readers that still live on `Hand` today. Each needs more
than a move, which is why they are last:

- **`get_hand_status_string`**, from `Hand.status_string`. The caller is a
  django-tables2 column accessor, `tables.A("status_string")` in `views/hand.py`.
  An accessor cannot call a reader, so this one will need a `render_status`
  method on the table class instead of an accessor.
- **`get_trick_counts_string`**, from `Hand.trick_counts_string`. Two callers:
  `interactive_hand.html` renders `{{ hand.trick_counts_string }}`, and
  `broadcast.py` calls the method when it sends the `table` SSE event. The
  template call is the one that has to become a context variable; the broadcaster
  can call the reader directly.
- **`get_auction_display_with_explanations`**, from
  `Hand.auction_display_with_explanations`. `auction.html` calls it as
  `{{ hand.auction_display_with_explanations }}`, and that template is included
  from `read-only_hand.html` and `carousel_style_auction.html` as well as being
  rendered directly by `_auction_context_for_hand` in `views/hand.py`. Every one
  of those render paths has to supply the context variable, so this is the
  fiddliest of the three.

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

There is no `test_readers.py` today, and we have not written one. The readers are
covered indirectly, through the view and model tests that already existed --
`test_table_view.py` is the one place that calls a reader (`get_display_skeleton`)
directly. Direct unit tests for the readers are worth adding, and are not yet
built; the point of the extraction is that they are now easy to write, since each
reader is a function over model instances with no request and no side effects.
