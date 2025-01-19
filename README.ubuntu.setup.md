On Hetzner (Ubuntu VERSION="24.04.1 LTS (Noble Numbat)") here's what (I can remember!) I had to do:

- `ssh root@hetz`, then

```shell
# apt update
# apt install htop docker.io
# adduser ubuntu # annoyingly interactive.  Be sure to use a secure password here; see below.
# usermod --append --groups sudo,docker ubuntu
# su - ubuntu
$ mkdir -vp ~/.ssh
$ cd .ssh
$ cat > authorized_keys # now paste your favorite ssh public key
$ exit
$ curl -fsSL https://tailscale.com/install.sh | sh && tailscale up # there's some link to tailscale.com that you gotta click on to authorize the new machine
$ exit
$ tailscale serve --bg 9000
```

- On my laptop:
  - update `~/.ssh/config` so that I can just "ssh hetz"
  - `docker context create remote --docker "host=ssh://ubuntu@hetz"`

- I haven't yet confirmed this, but I am pretty sure that a fresh Hetzner box allows ssh access via password (as opposed to restricting ssh access to ssh public key only).  Thus it's crucial that you use a decent password for the `ubuntu` user, and ideally, restrict ssh access to just public key, lest the automated Bad Guys p0wn your box.  Ask me how I know :-)

- Swap is handy!  It protects against the notorious OOM killer.  Set it up like this

```shell
   # fallocate -l 4g /mnt/4GiB.swap
   # chmod 600 /mnt/4GiB.swap
   # mkswap /mnt/4GiB.swap
   # swapon /mnt/4GiB.swap
   # echo '/mnt/4GiB.swap swap swap defaults 0 0' | tee -a /etc/fstab
```
