# Plan: add CrowdSec to the edge

**Status as of this commit: Phases 1 to 4 have landed; Phase 5 (enforcement) is
still intent.** The Caddy access log is on, CrowdSec is parsing it, the per-IP
rate-limit scenario raises alerts, and Prometheus scrapes both with a Grafana
dashboard over the top — see "Landed" at the bottom.

**Nothing is being blocked, and nothing is being reported to anyone**: there is
no bouncer, and CrowdSec is not registered with the central API.

**But decisions do exist, and that is not a contradiction.** The hub scenarios
ship with `remediation: true`, so when one of them fires it writes a real ban
decision. There is simply nothing installed that acts on a decision. The
practical consequence is worth stating plainly: **the moment Phase 5 installs the
bouncer, every unexpired decision already in the database starts blocking at
once.** Check `cscli decisions list` before that deploy, not after.

When a phase lands, move it into the "Landed" section and say what it actually
does.

Companion to [`crawler-repro.md`](crawler-repro.md), which records the two
outages this is meant to help with and the tiered rate limits we already deploy.

## What we want, and why

Two separate things, which happen to share one piece of software:

1. **Report offenders.** Somebody who collects a pile of `429`s from our rate
   limits is a repeat offender. We want to ban them outright for a few hours
   rather than shed each of their requests forever, and we want to tell the
   CrowdSec network about them.
2. **Consume the community blocklist.** Get the list of IPs other CrowdSec
   users have already reported, and refuse them at the edge before they cost us
   anything.

### How this relates to the rate limits we already have

The limits in `caddy/Caddyfile` stay exactly as they are. CrowdSec adds to
them; it replaces nothing. Being concrete about the two outages in
`crawler-repro.md`:

- **2026-07-15, single-IP crawler.** CrowdSec is a clear improvement. The
  `per_ip` zone sheds that crawler's requests one at a time, forever, and it
  keeps re-attacking. CrowdSec bans the source for hours after the first burst.
- **2026-08-04, distributed flood** (24,391 IPs, 2 to 4 requests each). A
  per-IP CrowdSec scenario is exactly as useless here as the `per_ip` zone was,
  and for the same reason: no single IP does anything worth noticing. The only
  part of CrowdSec that could help is the community blocklist, and only to the
  extent those IPs happen to be on it. The `list_views` and `whole_site`
  aggregate zones remain the thing that actually saves us.

So: do not loosen any zone because CrowdSec is now running.

## Decisions already made

Eric decided these on 2026-08-28; they are settled, not open questions.

- **Plugin bouncer, not the firewall bouncer.** The firewall bouncer drops
  packets before the TLS handshake and covers every port, which is genuinely
  cheaper, but it is host configuration on the Hetzner box that lives outside
  `just prod` and that we would have to remember to maintain. The plugin ships
  inside the image we already build, so a deploy carries it. We accept paying
  the TLS handshake for a banned IP.
- **Docker log datasource, not a shared log file.** CrowdSec reads the Caddy
  container's logs through the Docker socket it already mounts. No shared volume,
  no log rotation to get wrong. (Caddy writes to *stderr*, not stdout, which
  matters only because the datasource has to follow it — it does, by default.)
- **Start by observing, not enforcing.** Alerts get recorded, remediation does
  not happen. We read a week of what it *would* have banned before we let it ban
  anything. **This was implemented by omitting the scenario's `remediation`
  label, not by simulation mode** — see "Phase 3" under "Landed" for why that is
  the stronger guarantee.
- **No AppSec.** CrowdSec's AppSec component is a request-inspecting web
  application firewall: it looks at bodies, headers and paths for attack
  patterns, as a separate service the bouncer forwards requests to. That is a
  different problem from IP blocking, with its own false-positive budget. Out of
  scope. Do not build it because the plugin happens to support it.

## The constraint that shapes the design

**Only unmodified scenarios from the CrowdSec hub produce signals the network
accepts.** CrowdSec compares a content hash; custom scenarios you write, and
hub scenarios you edit even slightly, are ignored by the consensus engine. Worse
for us: free access to the full Community Blocklist is contingent on regularly
contributing signals. An engine that contributes nothing gets a "Lite" list
capped at 3,000 IPs instead.

This splits goal 1 from goal 2 in a way that was not obvious:

- Our "lots of `429`s" scenario is necessarily custom, because `429` means
  whatever the person doing the rate limiting decided it means. It will ban
  locally and contribute nothing.
- **Therefore we must also run the standard hub HTTP scenarios**, unmodified, or
  we do not earn the blocklist we came for. That is not a nice-to-have bullet at
  the end of the plan; it is the part that makes goal 2 work.

Both of those claims come from CrowdSec's own docs and we should re-read them
before Phase 5, because this is exactly the kind of policy that changes:
<https://docs.crowdsec.net/docs/central_api/community_blocklist/>.

## The pieces

### A new `crowdsec` container

- Image `crowdsecurity/crowdsec`, in the `prod` and `beta` compose profiles
  only, matching `caddy`. Dev and test are unaffected; `just runme` and `just
  dev` do not run Caddy, so there is nothing for CrowdSec to watch.
- Mounts `/var/run/docker.sock` read-only, for the log datasource.
- A named volume for `/var/lib/crowdsec/data`, so bans and the downloaded
  blocklist survive a restart. Without it every deploy forgets everyone.
- **Configuration must be baked into an image, not bind-mounted from `./crowdsec/`.**
  This is the same trap `caddy/Dockerfile` and `docker-compose-caddy.yaml`
  already have comments about: a bind mount resolves on the Docker *daemon's*
  filesystem, so a repo-relative path does not exist when we deploy over a
  remote context (`hetz-bridge`, `mini`). So: a thin `crowdsec/Dockerfile` that
  copies in the acquisition config, our parser and our scenario. (No
  `simulation.yaml` — we did not end up needing one. Hub collections turned out
  to be installed at *run* time from the `COLLECTIONS` environment variable
  rather than baked in at build time.)

### The bouncer plugin in Caddy

One more `--with` line in `caddy/Dockerfile`:

```
--with github.com/hslatman/caddy-crowdsec-bouncer/http
```

Only the `http` module. The repo also publishes `appsec` and `layer4` modules;
we want neither. Building `layer4` would drag in `caddy-l4` for no reason.

In `caddy/Caddyfile`, a global app block alongside the existing `order`:

```
{
    order crowdsec before rate_limit
    order rate_limit before reverse_proxy

    crowdsec {
        api_url {$CROWDSEC_API_URL}
        api_key {$CROWDSEC_API_KEY}
        ticker_interval 60s
    }
}
```

and a `crowdsec` directive in the site's handler chain — probably a new
`(crowdsec)` snippet imported by a second `caddy.import` label on `django`,
rather than stuffing it into `(ratelimit)`, since the two do different jobs and
the existing snippet's comment block is already about rate limiting alone.

**Why `crowdsec` runs before `rate_limit`.** A banned IP should be refused
before it touches any rate-limit bucket. If the order were reversed, a banned
flood would still eat the shared `list_views` and `whole_site` budgets on its way
to being rejected, which is precisely the harm those zones exist to prevent.

Streaming mode (the default) is what we want: the plugin pulls the decision list
every `ticker_interval` and answers from memory, so a request costs no round
trip. Leave `disable_streaming` alone. Leave `enable_hard_fails` alone too — we
do not want Caddy refusing to start, and thus the whole site down, because
CrowdSec is briefly unreachable.

### One secret: the bouncer's API key

Caddy authenticates to CrowdSec's local API with a key. Register it with a value
we choose rather than one CrowdSec generates:

```
cscli bouncers add caddy --key <value>
```

Choosing the value ourselves removes a start-order dependency — otherwise Caddy
needs a key that does not exist until CrowdSec has run once. It fits the
existing `*_FILE` secret pattern (`DJANGO_SECRET_FILE`,
`GOOGLE_OAUTH_CLIENT_ID_FILE`) and the `just ensure-django-secret` shape. It
must not be committed.

### Access logs (already on, as of Phase 1)

Caddy writes no per-site access log unless asked, and until Phase 1 we never
asked — so there was nothing for CrowdSec's hub scenarios to read, whichever
datasource we picked. Choosing the Docker datasource changes *where the log goes*
(container stderr instead of a file), not whether it exists.

That gap is now closed: `caddy.log.format: json` on the `django` service turns on
a JSON access logger. Details in "Landed".

Note this only ever concerned *access* logs. Caddy's own runtime log has always
been on stderr, and the rate-limit handler's `"rate limit exceeded"` line lives
there, which is why the `429` scenario needs no logging change at all. See
"Design: how the scenario knows whom to blame".

Two notes on volume, now that logging we never had is on:

- Access log lines are written when a request *finishes*. Our SSE streams are
  long-lived, so each one logs once, at close, not continuously.
- A `429` flood will be by far the loudest thing in this log. That is the point,
  but it means the log's size tracks attacks, not traffic.

## Design: how the scenario knows whom to blame

### The hazard

We have three rate-limit zones, and two of them — `list_views` and `whole_site`
— are *aggregate*: they shed requests based on total traffic from everybody.
During exactly the kind of distributed flood those zones exist for, **innocent
users get `429` too**. That is the design; the alternative is the site falling
over.

So a scenario that bans on "repeated `429`s" would risk banning real players
precisely when the site is under attack — converting an availability problem
into a "we banned our own users" problem. The scenario must be able to tell
*which zone* rejected a request, and act only on `per_ip`.

### Resolved: the zone is available three ways (checked against source, 2026-08-29)

I checked `caddy-ratelimit` at `master`. There is **no** per-zone or per-handler
response override in the zone config — the syntax is only `match`, `key`,
`window`, `events`, `ipv4_prefix`, `ipv6_prefix`, and the handler
unconditionally returns `caddyhttp.Error(http.StatusTooManyRequests, nil)` with
a nil message. So the idea of giving `per_ip` its own distinct status code is
not directly supported.

But the zone name is exposed three other ways, and the second one is what we
should use:

1. **A placeholder, `{http.rate_limit.exceeded.name}`**, set just before the
   error is returned and documented in the handler's doc comment. It holds the
   name of the zone whose limit was exceeded, and it is readable from
   `handle_errors` routes. This *does* give us a per-zone response override —
   not through zone config, but by branching in an error route on the
   placeholder, and emitting a different status or a marker header per zone.
   Workable, but it means writing an error route we would otherwise not need.

2. **A dedicated structured log line, which already contains everything we
   want.** On every rejection the handler logs, at `Info` level:

   - `msg`: `"rate limit exceeded"`
   - `logger`: `"http.handlers.rate_limit"` (the module ID)
   - `zone`: the zone name
   - `remote_ip`: the client
   - `wait`: how long until the limit clears
   - `key`: only when the `log_key` option is set

3. **A Caddy event**, `rate_limit_exceeded`, carrying `zone`, `remote_ip` and
   `wait`, which Caddy's `events` global option can bind a handler to. Complete
   for the record; far more machinery than we need.

### Consequence: parse the rate-limit log line, not the access log

Option 2 is strictly better than anything in the previous draft of this plan,
and it simplifies the work:

- **The zone is explicit**, so the scenario keys on `zone == "per_ip"` and
  ignores `list_views` and `whole_site` entirely. The false-positive hazard
  above disappears *by construction* rather than by hoping a threshold
  separates crawlers from reloading humans.
- **No Caddyfile change at all** for this half. This line is the handler's own
  runtime log, not a per-site access log, so it goes to Caddy's stderr whether
  or not we add a `log` directive, and `Info` is Caddy's default level. The
  Docker datasource picks it up as-is.
- **A custom parser costs us nothing.** CrowdSec's signal-validity rule is about
  *scenarios*: a custom or edited scenario is ignored by the consensus engine,
  but a custom parser has no effect on validity. Our `429` scenario is custom
  regardless, so parsing a non-standard log line loses us nothing we had.
- `log_key` stays off. For `per_ip` the key is `{remote_host}`, which duplicates
  `remote_ip`; for the aggregate zones it is the constant `static`. It would tell
  us nothing.

The `crowdsecurity/caddy` hub collection is still needed — but for the *other*
goal. It parses access logs, and the hub scenarios that run on top of it are what
earn the community blocklist. The two halves read two different logs, which is
why Phase 1 and Phase 3 are independent.

### The one caveat: `remote_ip` is the TCP peer, not `X-Forwarded-For`

The handler derives it with `net.SplitHostPort(r.RemoteAddr)`. It does not
consult any forwarded-for header. In our topology that is exactly right — Caddy
terminates TLS at the edge and is the first hop, the same assumption
`caddy/Caddyfile` already documents for `key {remote_host}`.

**But it means that if we ever put anything in front of Caddy** — a CDN, a load
balancer, Cloudflare — `remote_ip` silently becomes that proxy's address, and the
scenario would ban the proxy, taking out all traffic. If that day comes, this
scenario has to be revisited before the proxy goes live.

## Open question: ban duration

Untested. Our legitimate peak is 3.5 requests/second in the busiest minute of
two weeks, roughly 1000x below capacity, so there is enormous headroom and a
long ban costs us little in the normal case. The risk is not throughput, it is a
shared address: a school, an office, or carrier NAT means one ban can take out
everybody behind it. Start short (an hour or two) and lengthen it once we have
evidence.

## Phases

Each phase should be its own commit, and each is independently useful. Note that
the two goals read two different logs, so Phase 1 is a prerequisite for the hub
scenarios and the blocklist, but **not** for the `429` scenario in Phase 3.

**Phases 4 and 5 swapped on 2026-08-30**, so monitoring now comes before
enforcement. The reason is Phase 3: it is sitting in an observation week whose
whole output is counters and alerts, and reading those off a Grafana dashboard
beats reading them off `cscli metrics` by hand. Monitoring also cannot break
anything, so there is no reason to hold it behind the one phase that can.

That swap means **the numbering in this repository's git history is the old
one.** Commits up to and including "Alert on IPs that Caddy's per-IP rate limit
keeps rejecting" say "Phase 4" where they mean enforcement, which is Phase 5
here. Comments in the working tree have been corrected; commit messages, being
history, have not.

**Phase 1 — access logs. Done and verified on beta; see "Landed".**

**Phase 2 — the CrowdSec container, parsing but not enforcing. Done and verified
on beta; see "Landed".**

**Phase 3 — the custom `429` scenario, observation only. Built and verified; see
"Landed". The waiting is the part that remains.** Let it collect for a week, then
read `cscli alerts list` and answer honestly: did it flag anybody we recognise?
Tune the thresholds, or throw the scenario away.

**Phase 4 — monitoring. Done; see "Landed".**

**Phase 5 — enforce.** Add the bouncer plugin to `caddy/Dockerfile`, the global
block and the snippet import, and the API key secret. Add `remediation: true` to
the scenario, but only if Phase 3's observation week justified its thresholds.
Enrol with the central API (`cscli console enroll`) so we both contribute
hub-scenario signals and receive the community blocklist. Confirm the blocklist
actually arrived: `cscli decisions list` should show a large number of entries
with origin `CAPI` or `lists`, not just our own. Also consider
`enable_caddy_metrics` on the bouncer, which reports blocked-request counts
through Caddy's own `/metrics` — it cannot be done before the bouncer exists,
which is why it sits here rather than in Phase 4.

## How to test any of this

The same constraint as the rate limits, for the same reason: this lives at Caddy,
and **`just runme` and `just dev` do not run Caddy.** `just mini` deploys the
`beta,monitoring` profile with no main-branch or clean-tree guard, so it will
deploy this branch as-is.

**But a plain `just mini` does not exercise Caddy at all, and this is easy to
mistake for a working test.** Measured on 2026-08-29, two separate things stop
traffic reaching it, and you must fix both:

1. **`tailscale serve` owns port 443 on the tailnet interface.** Caddy binds
   `0.0.0.0:443`, but a request to the `.ts.net` name arrives on the Tailscale
   IP, where `tailscale serve` answers first and proxies straight to Daphne.
   Everything looks healthy — correct status codes, valid TLS, current
   `x-bridge-version` — while the edge you meant to test is bypassed entirely.

   **The reliable way to tell is Caddy's own access log**, not the response
   headers. Ask whether the request you just made shows up:

   ```
   docker compose logs caddy --no-log-prefix --tail 4000 |
       jq --raw-input --raw-output 'fromjson?
           | select(.logger == "http.log.access.log0")
           | [(.ts | floor | todate), (.status | tostring),
              .request.method, .request.uri, (.request.remote_ip // "-")]
           | join(" ")'
   ```

   Do **not** use the `Server:` response header for this. It is tempting and it
   is wrong: Caddy passes an upstream's `Server` header through untouched on
   reverse-proxied responses, so beta answers `server: daphne` *with Caddy fully
   in the path*. Measured on beta 2026-08-30, where the same request appears in
   Caddy's access log and still reports `server: daphne`. Caddy only says
   `server: Caddy` on responses it generates itself, such as a `429`.
2. **Caddy cannot get a certificate for a `.ts.net` name.** Reaching it directly
   from inside the container fails the handshake server-side with
   `tlsv1 alert internal error` (SSL alert 80), so it can serve nothing on that
   hostname. Fix with a *temporary* `caddy.tls: internal` label, exactly as
   `crawler-repro.md`'s step 2 describes — and do not commit it, since prod needs
   real public certificates.

`crawler-repro.md`'s "Testing the Caddy rate limit" section covers the rest,
including the trap where a failed handshake makes every request return status 0
and you see no `429`s, which looks like a broken limiter but is a non-result.

Beta avoids both problems: real Let's Encrypt certificates, nothing intercepting
443. For anything at the edge it is the more trustworthy target.

`project/app/manually_test_rate_limiting.py` is the natural way to generate the
`429`s that should trigger the scenario, and the fact that it floods from a single
IP — a caveat for other purposes — is exactly right here: the `per_ip` zone is the
only one the scenario watches. Watch for `zone=per_ip` in `just caddy-log`, and
then for a matching entry in `cscli alerts list`.

`just caddy-log` is the right lens for all of this: it already understands both
kinds of line we care about, the rate limiter's `"rate limit exceeded"` and (since
Phase 1) access entries with a `429` or 5xx status. Use
`docker compose logs caddy` when you need the lines it filters out.

## Landed

### Phase 1: the Caddy access log

One label on the `django` service in `docker-compose.yaml`:

```yaml
caddy.log.format: json
```

That is the whole change. It goes in a label rather than in `caddy/Caddyfile`
because that file's own header explains it holds only what "the labels can't
express cleanly", and a two-line `log` block is expressible cleanly.

What it produces, checked with `caddy adapt` against a site block of the shape
caddy-docker-proxy generates:

- An access logger with `encoder.format: json`, writing to stderr (the default
  writer), which Docker captures. There is no log file and nothing to ship.
- Caddy's `default` logger gains an `exclude` for `http.log.access.log0`, so
  access entries and runtime entries stay separate streams while both land on
  stderr. Access entries carry `logger: "http.log.access.log0"`.

`format json` is explicit rather than left to default because Caddy picks its
encoder from whether the writer is a terminal. The default would in fact be JSON
under Docker, but the format is a contract with whatever parses the lines, so it
should be stated rather than inferred.

**`just caddy-log` needed no change, and gets more useful.** Its jq already
filters on `.status == 429`, `(.status // 0) >= 500`, and `.request.*` — fields
that exist only in access entries, so those clauses have been dormant since they
were written. They now match. The recipe deliberately shows only 429s and 5xx
from the access log rather than every request, which is the right default.

**Config verified on the mini; traffic not.** After a `just mini` deploy,
Caddy's admin API returns exactly the shape `caddy adapt` predicted:

```
DOCKER_CONTEXT=mini COMPOSE_PROFILES=beta \
    docker compose exec caddy wget -qO- http://127.0.0.1:2019/config/logging

{"logs":{"default":{"exclude":["http.log.access.log0"]},
         "log0":{"encoder":{"format":"json"},"include":["http.log.access.log0"]}}}
```

So caddy-docker-proxy does convert the label into the `log { format json }` that
was validated. That was the one real risk, and it is closed. Use `127.0.0.1`
rather than `localhost` for that query: the admin endpoint listens on IPv4
loopback only, and `localhost` resolves to `::1` inside the container, which
answers "connection refused" and looks like a disabled admin API.

**Entries confirmed flowing, on beta.** The mini could not confirm it: no
request has ever reached Caddy there, for two pre-existing reasons neither
caused by this change (see "How to test any of this"). Since Caddy serves
nothing on the mini, nothing there exercises the access log, the rate limits, or
anything else at the edge.

Beta settled it. After deploying this branch, one request produced one entry:

```
2026-08-30T00:13:00Z 302 GET /player/1/ 97.113.55.114
```

alongside several `200 GET /.well-known/acme-challenge/...` entries from Let's
Encrypt validating the certificate. So the access log works end to end on a host
with real certificates and nothing intercepting 443, which is what Phase 1 set
out to do. Phase 2 has a log to read.

### Phase 2: CrowdSec, parsing and deciding nothing

Three new files — `crowdsec/Dockerfile`, `crowdsec/acquis.d/caddy.yaml`, and
`docker-compose-crowdsec.yaml` (added to the `include:` list in
`docker-compose.yaml`) — plus a `crowdsec` service in the `prod` and `beta`
profiles, a `just cscli` recipe, and one line in `_deploy`.

**`_deploy` needed changing, or none of this would ever start.** It only ups
services it names, which is why Caddy already had an explicit `up`; `crowdsec`
now rides along in that same prod/beta branch.

#### The part that decides whether any of it works

`crowdsecurity/caddy-logs` opens its filter with
`evt.Parsed.program startsWith 'caddy'`. Nothing in the Docker datasource sets
`program` — reading the source, it only attaches the acquisition's labels to each
line. What bridges the two is `crowdsecurity/non-syslog`, which copies
`labels.type` into `evt.Parsed.program` and which ships as a *second YAML
document inside `crowdsecurity/syslog-logs`*, not as a file of its own.

So the string `caddy` in `labels.type` is the whole connection between our logs
and the Caddy parser, and getting it wrong produces silence rather than an error.
`syslog-logs` is therefore named explicitly in `PARSERS` rather than left to
arrive as a dependency. It turns out the image installs `crowdsecurity/linux`
by default, which already brings it, so that is belt-and-braces — but it costs
nothing and does not depend on a default we do not control.

Two smaller things checked against beta's real logs before writing any config:
the Docker datasource follows stderr by default, which it must, since Caddy
writes both its logs there; and Caddy's access entries do carry the
`request.client_ip` field the parser reads, equal to `request.remote_ip` because
we configure no trusted proxies.

#### Verified on beta

`just cscli metrics`, after three requests:

```
| Source                 | Lines read | Lines parsed | Lines unparsed | Lines poured to bucket |
| docker:/server-caddy-1 | 3          | 3            | -              | 1                      |

| Parsers                            | Hits | Parsed | Unparsed |
| crowdsecurity/caddy-logs           | 3    | 3      | -        |
| crowdsecurity/non-syslog           | 3    | 3      | -        |

| Scenario                             | Current Count | Overflows | Poured |
| crowdsecurity/http-crawl-non_statics | 1             | -         | 1      |
```

The datasource found the container by pattern, every line parsed, none unparsed,
and a hub scenario is bucketing real requests. Note it reads from the current
tail rather than backfilling history, so these counts only ever cover lines since
the container started.

And the "decides nothing" half, all four checks:

- `cscli bouncers list` — empty. Nothing can act on a decision.
- `cscli decisions list` — "No active decisions".
- `cscli alerts list` — "No active alerts".
- `cscli capi status` — errors with "no configuration for Central API (CAPI)",
  which is `DISABLE_ONLINE_API` working. Nothing is reported upstream and no
  blocklist is pulled.

### Phase 3: the per-IP rate-limit scenario, alerts only

Two new files, both baked into the CrowdSec image:
`crowdsec/parsers/s01-parse/caddy-ratelimit.yaml` and
`crowdsec/scenarios/caddy-per-ip-ratelimit.yaml`.

#### We did not use simulation mode, and that is a deliberate change of plan

This plan originally said to put the scenario in simulation mode. We did
something stronger instead: **the scenario simply omits the `remediation` label.**

An overflow therefore produces an alert and *cannot* produce a decision — there
is nothing for a bouncer to act on, now or after Phase 5 adds the bouncer. That
is a better guarantee than simulation for two reasons. Simulation for a custom
scenario is keyed on the *file* name rather than the scenario name, a known
CrowdSec wrinkle, so a small mistake there enforces while you believe you are
only watching. And simulation is configuration that a later edit can quietly
undo, whereas a missing capability cannot be undone by accident.

Phase 5 adds `remediation: true`, and that edit is the moment this scenario
becomes able to ban anyone. Treat it accordingly.

#### The parser reads every zone; the scenario acts on one

The parser matches any `"rate limit exceeded"` line and records which zone
rejected the request in `evt.Meta.ratelimit_zone`. The scenario then filters to
`per_ip`.

Splitting it that way buys something the earlier draft of this plan did not have:
`cscli metrics` now counts rejections from `list_views` and `whole_site` too. That
is the measurement the aggregate-zone worry needs — we can see how often those
zones fire in practice — while keeping them structurally incapable of getting
anybody alerted on, let alone banned.

Thresholds are `capacity: 30`, `leakspeed: 10s`, `blackhole: 5m`, and they are
**provisional guesses**. Justifying or replacing them is the entire point of the
observation week.

#### Verified locally, end to end

Ran a local CrowdSec against a throwaway container named to match the
datasource's pattern, so real lines went through the real pipeline into real
buckets. `cscli explain` first, on three kinds of line:

| line | parsed by | reaches scenario |
|---|---|---|
| `zone: per_ip` rejection | `offby1/caddy-ratelimit` | `offby1/caddy-per-ip-ratelimit` |
| `zone: list_views` rejection | `offby1/caddy-ratelimit` | **nothing** |
| real access-log entry | `crowdsecurity/caddy-logs` | `crowdsecurity/http-crawl-non_statics` |

The middle row is the safety property, confirmed rather than assumed: an
aggregate-zone rejection is parsed and counted but reaches no scenario at all.
The third row confirms our parser does not disturb the hub path.

Then 40 rejections for a test address, through the datasource:

```
| Source                        | Lines read | Lines parsed | Lines poured to bucket |
| docker:/probe-caddy-ratelimit | 40         | 40           | 40                     |

 - Reason       : offby1/caddy-per-ip-ratelimit
 - Scope:Value  : Ip:203.0.113.77
 - Events Count : 31
 - Simulation   : false
 - Remediation  : false
```

`Events Count: 31` is capacity 30 plus the one that overflowed it, so the
threshold behaves as configured. `Remediation: false` is CrowdSec confirming the
scenario cannot ban, and `cscli decisions list` stayed at "No active decisions"
throughout.

One incidental lesson, worth knowing for any future test of this shape: the
Docker datasource attaches to a container when it *starts*, and then reads new
output. A probe container that prints and exits immediately is missed entirely —
the first attempt read zero lines. It has to stay alive long enough for CrowdSec
to attach before it writes anything.

#### Left for Phase 5

`/etc/crowdsec` is deliberately not a volume, so the agent regenerates its local
API credentials on each start — harmless while the agent and the local API share
a container. Phase 5 changes that calculation, because the central-API
credentials enrolment creates *do* need to survive a restart, and the obvious fix
of persisting `/etc/crowdsec` would shadow the baked acquisition config and then
never update it again. Solve that before enrolling, not after.

### Phase 4: Prometheus and a Grafana dashboard

Neither Caddy nor CrowdSec was being scraped: `prometheus/prometheus.yml` had
exactly two jobs, `django` and `postgres`. Phase 4 adds a job for each, plus one
dashboard, `grafana/dashboards/edge-caddy-crowdsec.json`.

#### Getting at Caddy's metrics without exposing its admin API

Caddy serves `/metrics` from its admin endpoint on port 2019 — which is bound to
localhost inside the container, and which can rewrite Caddy's entire
configuration. Binding *that* to the compose network so Prometheus could reach
some counters would be a poor trade.

So `caddy/Caddyfile` gains a second listener that serves metrics and nothing
else:

```
:2020 {
    metrics /metrics
}
```

`docker-compose-caddy.yaml` does not publish 2020, so it is reachable from the
compose network and nowhere else. No hostname means no automatic HTTPS, so
there is no certificate for Caddy to fail to obtain — the trap that makes the
mini useless for edge testing.

The global `metrics` option is also now set, which turns on the `caddy_http_*`
per-request family. It is the *global* option rather than `servers { metrics }`
because Caddy warns the nested form is deprecated and will be removed in the next
major version. Note the rate limiter's own counters appear either way, since the
plugin registers them itself.

#### The cardinality trap, which is a safety issue rather than tidiness

`caddy-ratelimit` reports each counter **twice**: once with `key=""`, the
aggregate for the zone, and once with `key` set to the actual bucket key. For the
`per_ip` zone that key is the client IP.

So the series count grows with the number of distinct addresses seen. In a flood
of the shape `crawler-repro.md` records — 24,391 addresses — Prometheus would
ingest a time series per attacking IP. That turns an attack on the web app into
an attack on the monitoring. The `caddy` job therefore drops every series with a
non-empty `key`:

```yaml
metric_relabel_configs:
  - source_labels: [key]
    regex: .+
    action: drop
```

Dropping whole series rather than the label is deliberate: a `labeldrop` would
collapse many series onto one identity and produce duplicate samples. What
survives is the zone-level aggregate, which is exactly what the dashboard graphs.

CrowdSec needed no configuration at all — its `config.yaml` already has
Prometheus enabled on `0.0.0.0:6060`.

#### The dashboard

Six panels, chosen for reading the Phase 3 observation week rather than for
completeness. Metric names were taken from the running instance on beta, not
guessed:

| panel | query |
|---|---|
| Rate-limit rejections by zone | `sum by (zone) (rate(caddy_rate_limit_declined_requests_total{key=""}[5m]))` |
| Requests reaching the limiter | `sum by (zone) (rate(caddy_rate_limit_requests_total{key=""}[5m]))` |
| Scenario overflows per hour | `sum by (name) (increase(cs_bucket_overflowed_total[1h]))` |
| Lines read and parsed | `cs_dockersource_hits_total`, `cs_parser_hits_ok_total`, `cs_parser_hits_ko_total` |
| Alerts by scenario | `sum by (reason) (cs_alerts)` |
| Active ban decisions by scenario | `sum by (reason) (cs_active_decisions)` |

The rejections-by-zone panel is the one the aggregate-zone worry has been waiting
for: `list_views` or `whole_site` appearing there means we are shedding traffic
from everybody, innocent visitors included.

Two notes for whoever edits this dashboard next. It hardcodes the Prometheus
datasource UID `PBFA97CFB590B2093`, copied from
`reasonable-looking-dashboard.json` because that one demonstrably works in this
deployment; the provisioned datasource in
`grafana/provisioning/datasources/datasource.yml` declares no explicit `uid`. And
dashboards are baked into the Grafana image rather than mounted, so a change
needs a rebuild, which `_deploy` does with `--build`.

#### Verified

`promtool check config` accepts the Prometheus file and Python parses the
dashboard JSON. `caddy validate` accepts the new Caddyfile blocks — run against
the stock Caddy image on the new directives alone, since the full file needs the
rate-limit plugin to parse.

#### What this immediately turned up

Within about ninety minutes of the Phase 3 deploy, beta's hub scenarios had
caught real scanners — `crowdsecurity/http-probing`,
`http-wordpress-scan`, `http-admin-interface-probing`,
`http-path-traversal-probing`, `http-sensitive-files`,
`http-cve-2021-41773` — and written ban decisions for several addresses in
Microsoft's `AS8075`. That is what prompted the correction at the top of this
document about decisions existing without a bouncer.

Our own `offby1/caddy-per-ip-ratelimit` has not fired, and neither has any
rate-limit zone: beta gets probed steadily but never fast enough to trip a limit.
That is a useful early data point for the observation week, and a hint that the
interesting numbers may only ever show up on prod.
