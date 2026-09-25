# Plan: cost controls for the AI-backed bot

**Status: proposal only. Nothing here is built.** Companion to
[`ai-bot-plan.md`](ai-bot-plan.md), which covers the bot's architecture; this covers
what stops it from running up an unbounded Anthropic bill if the project ever gets
real users (or automated abuse) and they all lean on the AI bot at once.

## The shape of the risk

Per-decision cost is already small and bounded (see `ai-bot-plan.md`'s cost table) --
a single request can't be expensive. The actual risk is *volume*: many hands, many
accounts, or a bug that loops, multiplying a small per-decision cost into a real
number. So the defenses below are about bounding volume and having a backstop for
when a bound fails, not about making any one request cheaper.

## Decisions

- **A provider-side hard spend cap, regardless of everything else.** Set a monthly
  spend limit in the Anthropic Console. This is the backstop that doesn't depend on
  any of our own code being correct: worst case, the API starts refusing requests
  instead of the bill running away. Do this before the bot ever talks to a real user,
  independent of and before any of the application-level work below.

- **Gate AI-bot access behind `Player.is_oauth_verified`, not a new mechanism.**
  `app/models/player.py` already has this property, with exactly this stated purpose:
  "OAuth users have been verified by a third-party provider... Use this to restrict
  privileged features... to reduce abuse potential." Plain username/password signup
  (`/signup/`, per `docs/README.api.md`) has no email verification at all today. This
  is the cheapest, already-built lever: require Google (or whatever OAuth) sign-in
  before a player may seat an AI bot. It won't stop a determined human, but it kills
  casual and most automated abuse -- a script farming free AI moves has to get through
  a real OAuth flow per account, for no payoff.

- **A finite per-account quota, with the dumb heuristics as the exhausted-quota
  fallback.** Track AI-assisted decisions (or hands) per account per period (e.g. per
  day). Once a player exceeds it, calls for their seat go through
  `make_standard_american_call()`/`slightly_less_dumb_play()` instead of the API --
  the same fallback `ai-bot-plan.md`'s "Resilience" section already designates for an
  API error or timeout. "Ran out of AI budget" and "the API is having a bad day"
  become the same code path: the bot gets dumber, not broken. This turns unbounded
  exposure into `(accounts) × (quota) × (cost per decision)` -- a number that can
  actually be computed and slept on.

- **A global kill switch.** One flag, checked before every AI call. If spend spikes
  for any reason -- a bug in the quota logic, a burst of signups, anything -- flip it
  off without a deploy, and every seat degrades to the dumb bot instead of the feature
  breaking or the bill climbing further.

- **Reuse the rate limiting this project already has**, rather than inventing a new
  mechanism. `caddy/Caddyfile`'s tiered rate limits and CrowdSec (`docs/perf/crowdsec-plan.md`)
  already exist for exactly this class of problem (see the 2026-07-15 and 2026-08-04
  incidents that plan documents). Apply the same shape to whatever action triggers an
  AI decision -- most likely "start a hand with an AI-controlled seat" -- rather than
  building bespoke throttling.

- **Watch spend, don't only cap it.** The project already runs Prometheus/Grafana
  (`docs/README.monitoring.md`). Log each decision's `response.usage` (tokens, model,
  cost) and graph the daily spend rate. An alert at "spend is trending toward 2x
  normal" gives hours of warning before anything would hit the hard cap -- the cap is
  for when every other layer failed, not the first line of defense.

## What was considered and set aside (for now)

- **"Please donate" box.** Fine as a nice-to-have, but it doesn't bound risk: someone
  can cost real money without ever seeing it, or donate once and then run thousands of
  hands. Not a substitute for anything above.
- **Track usage and email/beg for payment afterward.** This extends unsecured credit
  to strangers on the internet and hopes they pay retroactively. Cap spend *before* it
  happens rather than trying to collect after.
- **Full Stripe subscription billing.** A real option eventually, but bigger than it
  looks even with Stripe's basics -- webhooks, subscription state, dunning. Given the
  quota-plus-fallback design above already bounds the downside to a known number,
  monetization is a "nice problem to have once this is popular enough to matter," not
  a launch blocker.
- **Lighter-weight monetization, if it's ever wanted:** Stripe *Checkout* (their
  hosted payment page) for a one-time "buy N AI credits" purchase is much smaller than
  a subscription -- redirect to a Stripe-hosted page, handle one webhook that
  increments a credits counter. Worth remembering as the low-effort option if the
  "somehow pass the cost onto them" idea comes back later.

## Rough shape of the implementation (still just a sketch)

- **New field/model for usage tracking.** Likely a small model keyed by player and
  day (or a rolling window), incremented once per AI decision made on that player's
  behalf. A plain field on `Player` works too if only "today's count" is needed rather
  than history.
- **Config for the kill switch and quota values.** An env var or a secret file,
  following this project's existing pattern (`DJANGO_SECRET_FILE`,
  `GOOGLE_OAUTH_CLIENT_ID_FILE`) rather than hardcoding numbers.
- **One choke point.** Whatever function in the eventual AI bot driver decides "call
  Anthropic vs. fall back to the dumb heuristic" should check, in order: kill switch,
  quota remaining, `is_oauth_verified` -- so all three defenses live in one place
  rather than being scattered across the codebase.

## Phasing

1. **Do immediately, alongside wiring up the API at all:** the Anthropic Console
   spend cap, and the kill switch. Both are near-zero effort and have no reason to
   wait.
2. **Before any real user can reach the feature:** the `is_oauth_verified` gate, the
   per-account quota, and the dumb-bot fallback wired to both the quota and to API
   errors.
3. **Before or shortly after launch:** spend logging into the existing
   Prometheus/Grafana stack, with an alert threshold.
4. **If usage patterns warrant it:** rate limiting on AI-hand-starts via the existing
   Caddy/CrowdSec infrastructure.
5. **Only if this gets popular enough to matter:** Stripe Checkout credits, as the
   lightest monetization option, revisited then rather than designed now.
