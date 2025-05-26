# The bridge server has a little web API, with which it communicates with bots.

* The service is at https://bridge.offby1.info
* There's an alternative at https://beta.bridge.offby1.info, but as the name suggests, I don't try hard to keep that stable.

With it, you can:

- authenticate
- receive a transcript of a hand -- i.e., everything your player should know about it (your own cards, what calls and plays have already been made; the dummy's cards if they've been exposed)
- receive asynchronous notifications about calls and plays for a particular hand
- make calls and plays in that hand

## Authentication

Before you do anything else, you need to create a username and password.  That can only be done manually; use a normal web browser to go to `/signup/` and do the usual pick-a-username-and-password-and-reenter-the-password dance.

Now to authenticate your web client, have it make a GET (not a POST) to `/three-way-login/`, including a header like

    Authorization: Basic blahblahblah

where the `blahblahblah` is your username (e.g. `bob`), plus a `:`, plus your password, all base64-encoded.

For example, if your usename and password are `bob` and `sekrit`, here's a python snippet to to the base64-encoding:

    >>> base64.b64encode(b"bob:sekrit").decode()
    'Ym9iOnNla3JpdA=='

and here's that encoding in use:

    ❯ curl -H "Authorization: Basic Ym9iOnNla3JpdA==" http://localhost:9000/three-way-login/
    {"player-name": "bob", "player_pk": 1, "comment": "user=<User pk=1> used a regular password. Splendid."}%

Sometimes the response will include "table" and "hand" information:

    {"player-name": "bob", "player_pk": 1, "comment": "bob is already authenticated -- welcome", "table_pk": 5, "hand_pk": 9}

You'll need to save the various *`_pk` values to use in subsequent requests.

Here's an example using `curl` from the command line (notice how "curl" does all that base64 mumbo-jumbo for us):

    ❯ curl --cookie cook --cookie-jar cook -u 'bob:sekrit' -v http://localhost:9000/three-way-login/
    * Host localhost:9000 was resolved.
    * IPv6: ::1
    * IPv4: 127.0.0.1
    *   Trying [::1]:9000...
    * connect to ::1 port 9000 from ::1 port 54758 failed: Connection refused
    *   Trying 127.0.0.1:9000...
    * Connected to localhost (127.0.0.1) port 9000
    * Server auth using Basic with user 'bob'
    > GET /three-way-login/ HTTP/1.1
    > Host: localhost:9000
    > Authorization: Basic Ym9iOnNla3JpdA==
    > User-Agent: curl/8.7.1
    > Accept: */*
    >
    * Request completely sent off
    < HTTP/1.1 200 OK
    < Content-Type: application/json
    < X-Frame-Options: DENY
    < Vary: Cookie
    < Content-Length: 104
    < X-Content-Type-Options: nosniff
    < Referrer-Policy: same-origin
    < Cross-Origin-Opener-Policy: same-origin
    < Server-Timing: TimerPanel_utime;dur=192.3149999999998;desc="User CPU time", TimerPanel_stime;dur=3.157999999999994;desc="System CPU time", TimerPanel_total;dur=195.4729999999998;desc="Total CPU time", TimerPanel_total_time;dur=228.35237509571016;desc="Elapsed time", SQLPanel_sql_time;dur=12.828334234654903;desc="SQL 6 queries", CachePanel_total_time;dur=0;desc="Cache 0 Calls"
    < X-Bridge-Version: 35ce0b0b 2025-03-06
    < X-Bridge-Git-Symbolic-Ref: refs/heads/document-api
    * Added cookie csrftoken="6hwK1VGpisChVwlkIekOUSZy2Ac2T3U5" for domain localhost, path /, expire 1772739683
    < Set-Cookie: csrftoken=6hwK1VGpisChVwlkIekOUSZy2Ac2T3U5; expires=Thu, 05 Mar 2026 19:41:23 GMT; Max-Age=31449600; Path=/; SameSite=Lax
    * Added cookie sessionid="05ezdiqaivp90dfjcjf4gkae67lqt3le" for domain localhost, path /, expire 1742499683
    < Set-Cookie: sessionid=05ezdiqaivp90dfjcjf4gkae67lqt3le; expires=Thu, 20 Mar 2025 19:41:23 GMT; HttpOnly; Max-Age=1209600; Path=/; SameSite=Lax
    < Server: daphne
    <
    * Connection #0 to host localhost left intact
    {"player-name": "bob", "player_pk": 1, "comment": "user=<User pk=1> used a regular password. Splendid."}%

You'll notice two cookies in that response -- `csrftoken` and `sessiond`.  You'll need to store both of those; on subsequent requests, you need to resubmit them both:

- The sessionid value should be in your `Cookie` header (your http client might do this for you automatically)
- The csrftoken value should *either* be in its own header named `X-CSRFToken`, *or* you can include it as a form field named `csrfmiddlewaretoken` in every POST request. Both techniques work; use whichiever is convenient.

Example POST data with the csrftoken in a header:

    url http://localhost:9000/call/7/
    headers {'User-Agent': 'python-requests/2.32.3',
    'Accept-Encoding': 'gzip, deflate',
    'Accept': '*/*',
    'Connection': 'keep-alive',
    'X-CSRFToken': '6hwK1VGpisChVwlkIekOUSZy2Ac2T3U5',
    'Cookie': 'csrftoken=6hwK1VGpisChVwlkIekOUSZy2Ac2T3U5; sessionid=05ezdiqaivp90dfjcjf4gkae67lqt3le,
    'Content-Length': '7',
    'Content-Type': 'application/x-www-form-urlencoded'}
    data call=1N

Currently the only content-type I accept is `application/x-www-form-urlencoded`, but I assume I can easily add other flavors, like JSON or XML.

## Getting the transcript

(You can do this whenever you like, if you have gotten out of sync)

Do a GET to `/serialized/hand/`{hand_primary_key}`/`

An example transcript is in this directory: `example-xscript.json`.

## Receiving information from the server

The server uses [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) to asynchronously send information to its clients.

do a "long poll" or whatever you call it to (assuming your `player_pk` is indeed 1) `/events/player/system:player:1/`

You'll get something like this:

    at 2025-03-06T11:54:28-08:00 ❌130  ❯ curl --cookie cook --cookie-jar cook   https://django.server.orb.local/events/player/system:player:1/
    :

    event: stream-open
    data:

    event: keep-alive
    data:

You're guaranteed to get one event every (I think it is) 30 seconds, typically a "keep-alive".

many minutes pass, until someone does something interesting:

    event: keep-alive
    data:

    event: keep-alive
    data:

    event: keep-alive
    data:

    event: message
    id: system%3Aplayer%3A1:606
    data: {"new-hand": 23, "time": 1741290957.4350302, "tempo_seconds": 1.0}

    event: keep-alive
    data:

That last is the opening lead; the "dummy" is the actual cards (which if you "resolve" the unicode escape sequences is `♣4♣7♦4♦5♦J♥4♥6♥8♥Q♠2♠3♠6♠Q`)

## Make calls and plays

### calls

do a POST to `/call/`{hand_primary_key}`/`, with headers `Content-Type: application/x-www-form-urlencoded` and body like `call=Pass` or `call=1%E2%99%A3` (that's url-encoced; it means `call=1♣`)

### plays

do a POST to `/play/`{hand_primary_key}`/`, with headers `Content-Type: application/x-www-form-urlencoded`, and a body like `card=%E2%99%A52` (that's URL-encoded; it means `card=♥2`)
