On Hetzner (Ubuntu VERSION="24.04.1 LTS (Noble Numbat)") here's what (I can remember!) I had to do:

- `ssh root@hetz`, then

```shell
# apt update
# apt install -y htop docker.io
# # edit /etc/ssh/sshd_config
# # change `#PasswordAuthentication yes` to `PasswordAuthentication no`
# /etc/init.d/ssh restart
# adduser ubuntu # annoyingly interactive.
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

- I haven't yet confirmed this, but I am pretty sure that a fresh Hetzner box allows ssh access via password (as opposed to restricting ssh access to ssh public key only).  Thus it's crucial that you tweak /etc/ssh/sshd_config, lest the automated Bad Guys p0wn your box.  Ask me how I know :-)

  You could replace the entire /etc/ssh/sshd_config file, which is mostly comments and blank lines, with this
  ```
  Include /etc/ssh/sshd_config.d/*.conf
  PasswordAuthentication no
  KbdInteractiveAuthentication no
  UsePAM yes
  X11Forwarding yes
  PrintMotd no
  AcceptEnv LANG LC_*
  Subsystem sftp    /usr/lib/openssh/sftp-server
  ```

- Swap is handy!  It protects against the notorious OOM killer.  Set it up like this

```shell
   # fallocate -l 4g /mnt/4GiB.swap
   # chmod 600 /mnt/4GiB.swap
   # mkswap /mnt/4GiB.swap
   # swapon /mnt/4GiB.swap
   # echo '/mnt/4GiB.swap swap swap defaults 0 0' | tee -a /etc/fstab
```
