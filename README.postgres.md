# Miscellania
## What's the deal with e.g. `PGUSER` and `POSTGRES_USER`?

The latter is for the postgresql docker image, and (along with `POSTGRES_PASSWORD`) creates an initial user (it
defaults to `postgres`; the password has no default).  Without a valid password, I *think* the db won't even come up.
`PGDATABASE`, `PGHOST`, `PGPORT` and/or `PGUSER` are all for psql and presumably other postgres clients.

<https://www.postgresql.org/docs/current/libpq-envars.html>

## Wassup with port 5432

So I have done local, non-docker development with a MacOS version of postgres, which unsurprisingly listens on 5432.

I had the docker container also publish that port (`--publish 5432:5432`), and to my surprise, I can start the container and don't see an EADDRINUSE -- i.e., an error about some other process listening on that port.

I guess what's happening is: MacOS listens on localhost:5432, and docker notices that that port is in use, but says "that's OK, I'll listen on the various other internet interfaces".

```shell
+netstat:2> sudo lsof -P -n -iTCP -sTCP:LISTEN
OrbStack  14393 not-workme  104u  IPv4 0xe803de6e91421449      0t0  TCP *:5432 (LISTEN)
postgres  24832 not-workme    8u  IPv4  0xfa47b7317cc7112      0t0  TCP 127.0.0.1:5432 (LISTEN)
```
