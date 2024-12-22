On Hetzner (Ubuntu VERSION="24.04.1 LTS (Noble Numbat)") here's what (I can remember!) I had to do:

- `ssh root@hetz`, then

```shell
# apt update
# apt install htop docker.io
# adduser ubuntu # annoyingly interactive
# usermod --append --groups sudo,docker ubuntu
# su - ubuntu
$ mkdir -vp ~/.ssh
$ cd .ssh
$ cat > authorized_keys
$ curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up # there's some link to tailscale.com that you gotta click on to authorize the new machine
$ exit
# tailscale serve --bg 9000
```

- On my laptop:
  - update `~/.ssh/config` so that I can just to "ssh hetz"
  - `docker context create remote --docker "host=ssh://ubuntu@hetz"`
