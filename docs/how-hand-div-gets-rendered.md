# Who renders `hand-div.html`?

✓ `models.hand.send_HTML_update_to_appropriate_channel` via `app.views.hand._hand_HTML_for_player` which directly renders it

✓ `app.views.hand._everything_read_only_view` via including `read-only_hand.html` which includes `four-hands.html` which includes `hand-div.html`
  `four-hands.html` provides `id` and `cards`, so the view only needs to provide `active_seat`

✓ `app.views._interactive_view` renders `interactive_hand.html` which includes `carousel_style_auction.html` which includes `hand-div.html`

✓ `app.views._interactive_view` renders `interactive_hand.html` which includes `carousel_style_play.html`    which includes `hand-div.html`

## `hand-div.html` needs these variables:

- `active_seat` whose value is either the empty string, or one of "North", "East", "South", or "West".
- `cards` whose value is a somewhat complex pile of bootstrap buttons
- `class` whose value is a string that determines the CSS classes of the innermost container
- `id` whose value one of "North", "East", "South", or "West".
