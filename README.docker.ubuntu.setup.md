On Hetzner (Ubuntu VERSION="24.04.1 LTS (Noble Numbat)") here's what (I can remember!) root had to do:

- I think I had to log in through the crappy web console at first, to do this

```shell
# adduser ubuntu
# usermod -aG sudo ubuntu
# apt update
# apt install htop docker.io
# vigr # add "ubuntu" to the docker group, at the very bottom
# vigr -s # ditto
```

I still haven't figured out how to not have to type my password when running "sudo", but 🤷

- Still in the web console,

```shell
# su - ubuntu
$ mkdir -vp ~/.ssh
$ cd .ssh
$ cat > authorized_keys
```

- At this point I could abandon the web console and log in properly with ssh.

```shell
$ curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --auth-key=SEKRIT-OMITTED-ETC-ETC # from tailscale's web site; it auto-generates this command
$ sudo tailscale serve --bg 9000
```

- On my laptop:
  - update `~/.ssh/config` so that I can just to "ssh hetz"
  - `docker context create remote --docker "host=ssh://ubuntu@hetz"`
