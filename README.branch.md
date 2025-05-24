- `just restore < repro.sql`
- `just runme`
- Visit <http://localhost:9000/>
- Log in as bob
- Visit <http://localhost:9000/hand/1/>
- Observe: it's not my turn to call, but my cards have the light-green background
  (happily, the bidding-box's background is correct)

I think it's because, in `hand-div.html`, we have at the top

    <div id="{{ id }}" class="{% if id == active_seat %}active{% endif %}">

and as it happens, `id` is empty, and `active_seat` is also empty.

Now: what should `id` be in this case, and what should `active_seat` be in this case? 🤔
