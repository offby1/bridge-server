# Running it on MacOS

## enterprisedb

On MacOS, I'm running postgres from # https://www.enterprisedb.com/downloads/postgres-postgresql-downloads

After doing the setup, it says

    Installation Directory: /Library/PostgreSQL/16
    Server Installation Directory: /Library/PostgreSQL/16
    Data Directory: /Library/PostgreSQL/16/data
    Database Port: 5432
    Database Superuser: postgres
    Operating System Account: postgres
    Database Service: postgresql-16
    Command Line Tools Installation Directory: /Library/PostgreSQL/16
    pgAdmin4 Installation Directory: /Library/PostgreSQL/16/pgAdmin 4
    Stack Builder Installation Directory: /Library/PostgreSQL/16
    Installation Log: /tmp/install-postgresql.log

By default it listens on AF_INET, which means the command-line things require that I type a password :-(

## postgres.app

Previously I'd used https://postgresapp.com/ which was a bit confusing, but had the benefit of listening on an AF_UNIX socket by default.

## What's the deal with e.g. `PGUSER` and `POSTGRES_USER`?

The latter is for the postgresql docker image, and (along with `POSTGRES_PASSWORD`) creates an initial user (it
defaults to `postgres`; the password has no default).  Without a valid password, I *think* the db won't even come up.
`PGDATABASE`, `PGHOST`, `PGPORT` and/or `PGUSER` are all for psql and presumably other postgres clients.

## Wassup with port 5432

So I have done local, non-docker development with a MacOS version of postgres, which unsurprisingly listens on 5432.

I had the docker container also publish that port (`--publish 5432:5432`), and to my surprise, I can start the container and don't see an EADDRINUSE -- i.e., an error about some other process listening on that port.

I guess what's happening is: MacOS listens on localhost:5432, and docker notices that that port is in use, but says "that's OK, I'll listen on the various other internet interfaces".

```shell
+netstat:2> sudo lsof -P -n -iTCP -sTCP:LISTEN
OrbStack  14393 not-workme  104u  IPv4 0xe803de6e91421449      0t0  TCP *:5432 (LISTEN)
postgres  24832 not-workme    8u  IPv4  0xfa47b7317cc7112      0t0  TCP 127.0.0.1:5432 (LISTEN)
```
