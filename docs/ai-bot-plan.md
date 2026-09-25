# Plan: an AI-backed bridge bot

**Status: proposal only. Nothing here is built.** This sketches an architecture for
review before any code gets written, per the usual practice of agreeing on an approach
before implementing it.

## The problem

The only bot logic that exists today is deliberately dumb:
`bridge.auction.Auction.make_standard_american_call()` picks a call from a small
rule table, and `bridge.xscript.HandTranscript.slightly_less_dumb_play()` asks a
double-dummy solver for the objectively-best card, which plays perfectly but explains
nothing and doesn't simulate a partner with judgment. `cheating_bot.py` drives both,
polling the database directly for any hand where the current seat's player has
`allow_bot_to_play_for_me` set.

The idea: an bot whose calls and plays come from a Claude model instead, so a human can
get a partner (or opponents) with actual bridge judgment. Eric has already scoped this as
worth a few dollars in API spend; see the cost section below for why that's realistic.

## Non-goals

- Replacing `cheating_bot.py` or its double-dummy-solver play. That bot exists to keep
  hands moving along in stress tests and tournaments where nobody's watching; it should
  keep doing that unchanged.
- Teaching the model bidding conventions from scratch. It already knows standard
  American bidding from training; the job here is state-formatting and legality, not
  bridge pedagogy.
- Real-time chat with the bot. Interesting later, out of scope for a first version.

## Architecture: an external client against the existing bot API, not a new integration point

The project already has the exact seam this needs: `docs/README.api.md` plus
`project/app/reference_client.py`, which is a deliberately minimal, dependency-light
client (`requests` + `sseclient`) that any third party could write. The AI bot should be
another such client — logging in as a normal `Player`, reading
`/serialized/hand/<pk>/`, and posting to `/call/` and `/play/` — **not** a variant of
`cheating_bot.py` that reads the database directly. Two reasons:

1. It's the only interface this project promises to keep working for outsiders (see the
   "Nobody else's code calls this API today" note in `CLAUDE.md`), so building against
   it is free stress-testing of that promise.
2. It naturally respects the existing visibility rules (`app/visibility.py`,
   `docs/README.rapid-readers.md`): the transcript a client receives is already
   redacted to what that seat is allowed to see, so the bot cannot accidentally see
   opponents' cards the way something living inside the process boundary could.

Because this lives in the same repo, it can still depend on the `bridge` library the
server itself uses (`pyproject.toml` already pins it via git) — that's a public,
separately-versioned package, not an internal shortcut. In particular:

- `bridge.xscript.HandTranscript.from_python()` deserializes the `"xscript"` key from
  `/serialized/hand/<pk>/` straight back into a live object.
- `HandTranscript.auction.legal_calls()` and `HandTranscript.legal_cards(some_cards=...)`
  already compute exactly the legal-move set the server itself uses to validate `/call/`
  and `/play/` (`Auction.raise_if_illegal_call`). The bot should call these directly
  rather than re-deriving bridge rules or trusting the model to know them.
- `HandTranscript.next_seat_to_play()` (and the equivalent on `Auction`) tells the bot
  whose turn it is, which the SSE stream does not say directly — see below.

## Decision loop

One process per AI-controlled seat (matching the API's "one login, one seat" shape):

1. Log in (`/login/`), as with any bot account.
2. Subscribe to `/events/player/json/<player_pk>/`. Per `docs/README.sse.md`/
   `docs/README.api.md`, the events that matter are `new-call`, `new-play`, and
   `contract`; none of them say "it's your turn," so treat any of them (plus the
   initial connection) as "something changed, go check."
3. On each such wakeup, `GET /serialized/hand/<pk>/`, deserialize the `xscript`, and ask
   the bridge library whose turn it is. If it's not this seat, go back to waiting.
4. If it is: compute the legal set (`legal_calls()` or `legal_cards()`), build a prompt
   (below), call Claude with a single tool whose input is constrained to that set, parse
   the tool call, and POST the result to `/call/` or `/play/`.
5. Treat a 4xx from that POST as "state moved under us" (a human took the seat back via
   `allow_bot_to_play_for_me`, or a race with another update) — re-fetch the transcript
   and either drop this turn or retry, rather than treating it as a bug to fix.

No new SSE event type, channel, or endpoint is needed — which is good, because
`docs/README.sse.md` is explicit that a third endpoint is almost certainly a mistake and
the project has already been burned by the six-connections-per-origin limit once.

## Prompt shape and why tool use, not MCP

Reach for **Claude API + tool use** (a manual loop, or the SDK's tool runner), not MCP.
MCP solves "let a general-purpose chat client discover and call tools I expose" — useful
if a human wanted to literally hand their seat to Claude Desktop and chat about the game.
That's a plausible phase-3 idea (see below) but it's the wrong shape for "a background
process needs to pick one legal call or card, over and over, unattended." Building an
MCP server here would mean standing up a protocol layer to serve exactly one client we
also wrote, for no benefit over calling the tool directly.

Per turn:

- **System prompt** (cached): a fixed "rules primer" — standard American conventions,
  scoring, how to read the transcript format, general strategic guidance — plus both
  partnerships' agreed conventions (own side and opponents'; see "Partnership
  conventions" below). All of this is static across every decision this process makes
  until somebody's partnership changes, so mark it `cache_control: {"type":
  "ephemeral"}` and it's read from cache (~10% of normal input cost) on every call after
  the first.
- **User content** (fresh, small): dealer, vulnerability, the auction or the current
  trick so far, this seat's hand, dummy's hand if exposed, and the *explicit legal-move
  list* computed in step 4 above.
- **One tool**, e.g. `make_call(call: enum[...])` or `play_card(card: enum[...])`, whose
  enum is populated from that turn's legal set. This is the actual legality enforcement —
  the model physically cannot express an illegal move — with the server's own
  `raise_if_illegal_call`/`legal_cards` check as the backstop in case of a library-version
  mismatch or a bug in this new code.
- The `/call/` endpoint already accepts an optional `explanation` field
  (`reference_client.py`'s `call()` takes one). Worth having the model fill it in with a
  one-line rationale — free UI value (a human partner can see *why* the bot bid what it
  bid) for no extra request.

### Resilience

If the Claude call fails or times out, fall back to
`make_standard_american_call()`/`slightly_less_dumb_play()` rather than stalling the
hand — both already exist and are exactly what a timeout should degrade to.

## Partnership conventions

Knowing *that* partner opened "two clubs" isn't enough; the bot also needs to know
whether this partnership's agreement makes that strong, weak, or something else — and
for the same reason, it needs the opponents' agreements too, to interpret *their*
auction. Real bridge solves this with a convention card attached to a partnership for
the whole session, not re-declared hand by hand, and the design here should match that.

That argues against adding "N/S conventions" / "E/W conventions" slots to
`HandTranscript`/`xscript`: that structure is rebuilt and re-serialized on every single
call and play, so anything static placed inside it gets duplicated on every request and,
worse, sits inside the part of the prompt that changes every turn — exactly where it
*can't* benefit from prompt caching the way the rules primer does.

Instead, conventions belong to the partnership relationship, which is where the
project already models "these two players are playing together": `Player.partner` in
`app/models/player.py` (a mutual FK set by `partner_with`/`break_partnership`; there's no
separate `Partnership` model today). A free-text conventions field belongs there — on
`Player` itself, or promoted to a real `Partnership` model if this grows into something
versioned or structured. It should be exposed through the API separately from
`/serialized/hand/<pk>/` — e.g. alongside `/login/`'s response, or a small dedicated
read — so a bot fetches its own side's and the opponents' agreements once per session (or
again when a `PARTNERSHIPS` SSE event fires, since `app/sse_events.py` already has that
channel for partnership changes) and folds them into its cached system prompt, rather
than re-fetching and re-transmitting them with every hand.

## Model choice and cost

Bidding runs roughly 8-20 calls per hand across all four seats; play is up to 52 card
plays (13 tricks × 4, though declarer plays dummy's cards too). A process controlling one
seat (a human's partner) makes on the order of 15-20 decisions per hand; controlling
three seats (both opponents plus partner) is more like 40-50.

Per-decision cost is small regardless of model, because the system prompt caches and the
per-turn state is compact (order of a few hundred fresh tokens, tens of tokens of
output):

| Model | Price ($/MTok in, out) | Rough cost/decision | Rough cost/hand (1 AI seat, ~18 decisions) |
|---|---|---|---|
| Haiku 4.5 | $1 / $5 | ~$0.001 | ~$0.02 |
| Sonnet 5 | $2 / $10 | ~$0.0025 | ~$0.05 |
| Opus 5 | $5 / $25 | ~$0.006 | ~$0.11 |

(These are order-of-magnitude estimates assuming a healthy cache hit rate on the system
prompt — verify against `response.usage.cache_read_input_tokens` once built, per
`shared/prompt-caching.md`'s silent-invalidator checklist.)

Recommendation: **default to Sonnet 5**, with the model configurable per bot account so
it's cheap to try Haiku for high-volume/background seats or Opus for "this partner should
actually play well" seats. Even at the high end, a whole evening of hands costs low
single-digit dollars -- for one person, playing casually. What actually bounds cost once
real users are involved (spend caps, per-account quotas, a kill switch, falling back to
the dumb heuristics) is its own document: [`ai-bot-cost-controls-plan.md`](ai-bot-cost-controls-plan.md).

## Where this lives

A new Django management command, e.g. `app/management/commands/ai_bot.py`, run the way
`just notifier` runs the notifier natively — `just ai-bot`, say — reusing the project's
existing `uv`-managed venv (which already has `bridge`; add `anthropic` as a dependency)
rather than inventing a separate deployment unit. It needs its own secret file for the
Anthropic API key, following the existing pattern for `DJANGO_SECRET_FILE` and the Google
OAuth secrets: a file under `info.offby1.bridge`'s config directory, never committed,
read by the command at startup.

It should authenticate as an ordinary `Player`/`User` — no schema changes needed. Which
existing bot-related fields (if any) mark "this seat is AI, not `cheating_bot`, and not a
human who flipped on `allow_bot_to_play_for_me`") is worth a separate small design pass
once this is proven out; that's a Player/UI question, not an architecture one.

## Testing

Following the project's usual pattern (`app/test_reference_client.py` drives
`reference_client.py` against a real `live_server`): write the AI bot's HTTP/SSE glue so
it's driven the same way, but stub the Anthropic call in `just ft`/`just test` — record a
handful of representative (prompt → tool call) fixtures rather than hitting the real API
in the default suite, which would make tests slow, flaky, and billed. A separate,
explicitly-opt-in test (env-var gated) that hits the real API is reasonable for occasional
manual verification, mirroring how this project treats other real-network dependencies.

## Phasing

1. **Proof of concept.** One AI-controlled seat, run locally, playing against the
   existing dumb bots or a human, driven entirely through the public API. Confirms the
   legality-via-enum approach actually keeps the model from ever proposing an illegal
   move, and gives a real cache-hit-rate and cost number instead of the estimate above.
2. **Make it a first-class option.** Docker Compose service (own profile, so `just dev`
   doesn't require an API key), UI affordance for "seat an AI here" alongside the
   existing bot-flag checkbox.
3. **Stretch: MCP as a second, human-facing surface.** Once the tool-use core works,
   exposing "read this hand's transcript" / "make this call" / "play this card" as MCP
   tools would let a human point Claude Desktop (or Claude Code) at their own seat and
   discuss strategy interactively, as a different feature from the autonomous bot. Not
   needed for the core idea; only worth doing if that specific interactive use case is
   wanted later.
