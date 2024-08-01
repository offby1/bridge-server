# perf notes

How I managed to get py-spy working.  It wasn't easy.

I tried to run py-spy, but

* that requires root on MacOS (my development platform of choice)
* I couldn't figure out how to get it working via "sudo"
* I wound up using orbstack's "machine" like this:
- `git clone /Users/not-workme/git-repositories/me/bridge/server bridge-server`
- `cd bridge-server/project`
- `py-spy record --subprocesses poetry run pytest`

I seem to recall things failing mysteriously until I manuall accepted the gitlab SSH server's "fingerprint":

    $ ssh git@gitlab.com
    The authenticity of host 'gitlab.com (172.65.251.78)' can't be established.
    ED25519 key fingerprint is SHA256:eUXGGm1YGsMAS7vkcx6JOJdOGHPem5gQp4taiCfCLB8.
    This key is not known by any other names
    Are you sure you want to continue connecting (yes/no/[fingerprint])? yes
    Warning: Permanently added 'gitlab.com' (ED25519) to the list of known hosts.
    PTY allocation request failed on channel 0
    Welcome to GitLab, @offby1!
    Connection to gitlab.com closed.

## Thoughts about state

So ... I never put a lot of thought into what, exactly, should live in the db; and of that stuff, what should be immutable.

Despite whatever code I've written up to this point, I think:

* django auth stuff -- usernames, passwords, &c.  That should be mutable to the point that people can change their usernames, passwords, email addresses.

* *history* -- which players did what, and in what order.  This should be append-only.

    - when four players join at a "table" -- which might not need to be a first-class model, that should get recorded as the first entry in some record.
      - the record should include which cards got dealt to which player
    - when any player makes a legal call, that gets appended.
    - when any player makes a legal play, that gets appended.
    - when any player abandons a table, that gets appended.
    - and uh maybe that's it?

  Figuring out the current state of a player would mean finding their most recent action:
    - if there aren't any, they're in the lobby.
    - if the most-recent action was to abandon a table, they're in the lobby.
    - otherwise they're at the table indicated by the action
      - in which case we need to replay all the actions at the table -- there won't be all that many -- to see what cards he holds, whose turn it is to do what, &c
