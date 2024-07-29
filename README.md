It occurs to me ...

... when I first started working on this, I figured I'd use flask for the web server, since that's what I was used to.

But since then, I've gotten a new job, at which I use Django all day every day.  And it's clear Django gives me, for free, lots of stuff I'd need -- specifically a user database and basic auth, plus an ORM.

I'd expect to have these models:
* a hand of bridge
* users (gotten for free from django.contrib.admin or whatever it is)
* a tournament (many players, many hands)
* perhaps partnerships (two players)
* perhaps teams (> 1 partnerships, or > 1 players)
