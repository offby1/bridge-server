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

**Every page navigation leaks one stream for about a minute.** We added
`app/middleware/sse_stream_log.py` to log each stream's open and close. Lining the
opens up against the access log settles it:

    21:15:42  GET /player/       opened stream #6   (1 open)
    21:15:53  GET /players/      opened stream #8   (4 open)
    21:15:55  GET /tournament/   opened stream #9   (5 open)
    21:15:56  GET /tournament/   opened stream #10  (5 open)
    21:15:57  GET /tournament/1/ opened stream #11  (6 open)  <- cap reached
    21:16:53  streams #6, #7 and #11 closed after 55-70s

`base.html` put the bot-checkbox stream on every page, so each navigation opened a new
one while the departed page's stream stayed open for another 55 to 70 seconds. Six
navigations inside a minute -- logging in, creating a partner, creating a tournament,
opening it -- exhausted the budget. That is ordinary clicking, not unusual usage.

**The server, not the client, always ends these streams.** Every close we logged was a
`CancelledError`; none was a clean exhaust. `django_eventstream/views.py:227` writes a
keep-alive only every 20s and cannot detect a departed client until a write fails, so
a stream outlives its page by one to three keep-alive cycles.

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

## The fix

`base.html` now attaches `sse-connect` only when `user.player.current_hand` is set,
which is where the checkbox can actually change underneath the viewer. Everywhere else
it renders the same checkbox with no stream attached. That removes one leaked socket
per page view across the whole site.

`app/middleware/sse_stream_log.py` stays in place. It costs nothing when no stream is
open and it turns any recurrence into a log line instead of an afternoon.

Two smaller consumers remain, and we left both alone for now:
`django_browser_reload` (dev only) and the chat stream
(`app/templates/chat-partial.html:34`, only on pages with chat).

Two other approaches we considered and did not take. Serving dev over TLS would get
browsers onto HTTP/2, which multiplexes roughly 100 streams over one connection; that
raises the ceiling but hides the leak rather than fixing it. Shortening
django-eventstream's keep-alive would shrink the window in which a departed page's
stream lingers, but the interval is hardcoded.

## Still open

- **`/hand/1/` shows that nobody has called**, even with "Computer plays this hand for
  me" toggled and the bot visibly working. This reproduces on `main` as well, so it is
  not an upgrade regression. It is plausibly the same root cause, because a hand page
  opens several long-lived streams (`bridge-game.js:12`, `bridge-game.js:51`, the chat
  stream, plus `django_browser_reload`) and the updates arrive over exactly the
  connections that cannot be established. Retest this now that the fix has landed; if
  it persists, the SSE stream log will show whether those streams ever opened.

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
