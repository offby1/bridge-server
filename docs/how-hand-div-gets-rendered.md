# Who renders `hand-div.html`?

✓ `app.views.hand._hand_HTML_for_seat` renders it directly, for the per-seat SSE update.
  Its callers are `Hand.send_HTML_update_to_appropriate_channels` (in
  `app.models.hand`), which `app.broadcast.broadcast_after_play` calls when the
  `app_play` trigger fires.

✓ `app.views.hand._everything_read_only_view` via including `read-only_hand.html` which includes `four-hands.html` which includes `hand-div.html`
  `four-hands.html` provides `id` and `cards`, so the view only needs to provide `active_seat`

✓ `app.views.hand._interactive_view` renders `interactive_hand.html` which includes `carousel_style_auction.html` which includes `hand-div.html`

✓ `app.views.hand._interactive_view` renders `interactive_hand.html` which includes `carousel_style_play.html`    which includes `hand-div.html`

## `hand-div.html` needs these variables:

- `active_seat` whose value is either the empty string, or one of "North", "East", "South", or "West".
  It comes from `Hand.active_seat_name`.
- `cards` whose value is a dict keyed by suit name -- `Spades`, `Hearts`, `Diamonds`,
  `Clubs` -- each holding a list of already-rendered card markup. `_get_card_html` builds
  it, so whether a card is a clickable button or inert text is decided there, not here.
- `class` whose value is a string that determines the CSS classes of the innermost container
- `id` whose value is one of "North", "East", "South", or "West" -- except from
  `four-hands.html`, which passes it lowercase, so the `id == active_seat` comparison that
  applies the `.active` class never matches there.
