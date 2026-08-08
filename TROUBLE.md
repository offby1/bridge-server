# Trouble: pages hang while loading (investigated 2026-08-08)

## Summary

Pages hang because Chrome runs out of connections, not because the server is slow.
The `django-6.1` upgrade is not responsible; the same latent defect exists on `main`.

We started this investigation intending to `git bisect` the Django 6.1 upgrade. Don't.
The two commits under suspicion (`94b55013`, `13f22160`) cannot cause this, and the
evidence below points somewhere else entirely.

## What we confirmed

**The server is fast; the browser never sends the request.** A HAR capture of a hung
"Sign Me Up, Daddy-O" click shows:

    POST /tournament/signup/1/   total=42298ms   blocked=42213ms   wait=82ms

`blocked` is time Chrome spent in its own queue before opening a socket. The server
handled the request in 82ms once it finally arrived. While the same page was hung,
`curl` answered in 37ms.

**Chrome sits at exactly its per-origin socket cap.** During a hang, `lsof -nP
-iTCP:9000` showed six `ESTABLISHED` connections owned by Chrome and six matching
ones owned by the dev server. Six is Chrome's HTTP/1.1 limit per origin, shared
across all tabs. With all six consumed, every further request queues in the browser
until one frees up, which is why the page eventually unsticks on its own.

**Six sockets for two streams means they leak.** `/tournament/1/` opens only two
long-lived connections: the bot-checkbox stream (`project/app/templates/base.html:40`)
and `django_browser_reload` (enabled in `dev_settings.py`). The bot-checkbox stream
re-dials roughly once a minute, and each previous socket stays `ESTABLISHED` on both
ends instead of closing. Four re-dials appeared in two minutes of idling.

**The reconnects are already backing off.** A later HAR shows one stream ending after
40s and its replacement starting 15s afterward. `ReconnectingEventSource` begins at
about 3s and escalates, so a 15s delay means the stream had been flapping for a while
before that capture began.

## What we ruled out

- **Django 6.1.** We diffed the installed packages, not just the lockfile.
  `django/core/handlers/asgi.py` is byte-identical between 6.1rc1 and 6.1 final. The
  hang also reproduces under `--noasgi`, which bypasses the 6.0-to-6.1 ASGI handler
  rewrite completely.
- **daphne.** 4.2.2 to 4.2.3 is ruff reformatting plus two new `--websocket-max-*-size`
  flags.
- **The django-prometheus downgrade.** 2.5.0.dev3 to 2.4.0 looks alarming because the
  DB `ENGINE` and two middlewares come from it, but the diff is purely cosmetic:
  removed `pass` statements, de-indented `else:` branches, and a missing trailing
  newline.
- **A redirect on the stream.** We chased a 302 that turned out to belong to the POST
  row in DevTools, not to the events row.

## Correction: `just runme` is not a WSGI control

`base_settings.py` lists `"daphne"` at index 1 of `INSTALLED_APPS`, and daphne ships
its own `runserver` management command. Django's `get_commands()` iterates
`reversed(apps.get_app_configs())` and updates a dict, so the earliest app wins.
Both `just dev` and `just runme` therefore run daphne over ASGI. The log confirms it:
thread names read `ThreadPoolExecutor-149_0` (asgiref's per-request
`ThreadSensitiveContext` executor) rather than WSGI's `Thread-N
(process_request_thread)`.

Pass `--noasgi` to `just runme` when you actually want Django's WSGI dev server.

## Why production is probably unaffected

Caddy terminates TLS for the prod and beta profiles, so browsers negotiate HTTP/2 and
multiplex roughly 100 streams over a single connection. The six-socket ceiling applies
to `just runme` and `just dev`, which both serve plain HTTP/1.1. We have not verified
this against production.

## Still open

- **What makes the bot-checkbox stream flap.** `django_eventstream/views.py:227` emits
  a keep-alive every 20s and never ends the stream itself, and a healthy stream stayed
  open for over five minutes in one capture. Something intermittent drops it, and each
  drop pins another socket. The next step we chose is to log every stream open and
  close, with a reason, so the next occurrence explains itself instead of costing
  another afternoon.
- **Why a closed stream's socket stays `ESTABLISHED`** on both ends rather than being
  released.
- **`/hand/1/` shows that nobody has called**, even with "Computer plays this hand for
  me" toggled and the bot visibly working. This reproduces on `main` as well, so it is
  not an upgrade regression. It is plausibly the same root cause, because a hand page
  opens four long-lived streams (`base.html:40`, `bridge-game.js:12`,
  `bridge-game.js:51`, plus `django_browser_reload`) and the updates arrive over
  exactly the connections that cannot be established. We have not confirmed that.

## Unrelated: Google OAuth on `django.server.orb.local`

Google rejects the redirect URI registration, not our code. `.orb.local` is not a
public domain and the callback runs over plain HTTP, so the app fails Google's OAuth
2.0 policy for keeping apps secure. Register a `http://localhost` redirect URI, which
Google exempts, or use a real hostname with TLS. No amount of bisecting touches this.

## Reproducing and diagnosing

Reproduction is intermittent; the page hangs after the streams have flapped enough
times to consume all six sockets. While a page is hung:

    # Is the server even involved? (read-only GET)
    curl -sS -o /dev/null -w 'ttfb=%{time_starttransfer}s code=%{http_code}\n' \
        http://localhost:9000/tournament/1/

    # Count Chrome's sockets against the cap
    lsof -nP -iTCP:9000 | grep -v LISTEN

In DevTools, tick **Preserve log** before clicking; a form POST is a navigation and
clears the Network panel otherwise. Read the **Timing** panel: time under "Stalled" or
"Queueing" means the browser held the request, and time under "Waiting (TTFB)" means
the server did. Export the sanitized HAR to capture it.

Note that `RequestLoggingMiddleware` (`app/middleware/simple_access_log.py:19`) starts
its clock at its own position in the chain, so its `ms=` figure excludes every
middleware listed before it in `base_settings.py`, and it never sees responses those
outer middlewares generate.
