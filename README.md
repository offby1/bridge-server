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

    $ ssh git@gitlab.com                                                                                                                ─╯
    The authenticity of host 'gitlab.com (172.65.251.78)' can't be established.
    ED25519 key fingerprint is SHA256:eUXGGm1YGsMAS7vkcx6JOJdOGHPem5gQp4taiCfCLB8.
    This key is not known by any other names
    Are you sure you want to continue connecting (yes/no/[fingerprint])? yes
    Warning: Permanently added 'gitlab.com' (ED25519) to the list of known hosts.
    PTY allocation request failed on channel 0
    Welcome to GitLab, @offby1!
    Connection to gitlab.com closed.
