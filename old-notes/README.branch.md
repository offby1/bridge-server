# Thinking out loud

https://github.com/fanout/django-eventstream?tab=readme-ov-file#django-eventstream

django-eventstream seems pretty simple.  It should be all I need to get chatting-between-players, and alerting-a-player-of-wassup-at-their-table, working.

I'll have to write a bit of javascript, but it ought to be doable.

## Chat

### Lobby

Every player in the lobby should be "subscribed" to a "channel" for the lobby.
Every player in the lobby can post to that channel; of course their post goes to everyone.
Once they're seated at a table, they no longer can post, nor receive those posts.

### Partner

- Every player without a partner (and, by implication, not seated at a table) can communicate to any other player without a partner.
  This is similar to the lobby, except the channel is 1:1, not 1:many.

- Once they get a partner, they can *also* communicate privately with that partner.

- Once they get seated at a table, they lose the ability to communicate with partnerless players (again, this is similar the lobby thing).  They *keep* the ability to communicate with their partner, though, until ...

- Once an auction starts, and until the play is completed (or the table is prematurely broken up), they cannot communicate with anyone at all.

## Table actions

## SSE Readings

- <https://web.archive.org/web/20121115183325/http://curella.org/blog/django-push-using-server-sent-events-and-websocket/>
  Thoughtful but outdated (August 2012).  Interesting mostly to learn *why* the dude wanted server-sent events.

- <https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events>
  Decent description of the protocol

- <https://html.spec.whatwg.org/multipage/server-sent-events.html>
  Similarly-decent description.  Says "non-normative", which I guess means "this isn't actually a standard", but I bet it *is* the standard, in practice.
