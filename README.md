# Wassup homies
It occurs to me ...

... when I first started working on this, I figured I'd use flask for the web server, since that's what I was used to.

But since then, I've gotten a new job, at which I use Django all day every day.  And it's clear Django gives me, for free, lots of stuff I'd need -- specifically a user database and basic auth, plus an ORM.

I'd expect to have these models:
* a hand of bridge
* users (gotten for free from django.contrib.admin or whatever it is)
* a tournament (many players, many hands)
* perhaps partnerships (two players)
* perhaps teams (> 1 partnerships, or > 1 players)

## TODO
- make it super-easy for newcomers to start using it.
  This means: don't force them to generate a username and password; ideally they should be able to use passkeys.
  https://github.com/mkalioby/django-passkeys looked promising but that library is clearly intended solely for use by its author; the README is sloppily-written, there is essentially no documentation, error handling is useless.

  Unfortunately it's all that comes up when I go to https://djangopackages.org/ and type "passkey" in the search box.
  - find some alternatives -- <https://gitlab.com/offby1/auth_toy> has lots of experiments, iirc
  - [a dude on discord](https://discord.com/channels/856567261900832808/857642132423704577/1267558555725205625) recommends "Cloudflare Zero Access and PersistentRemoteUserMiddleware", whatever those are.  Looks very enterprise-y :-(
