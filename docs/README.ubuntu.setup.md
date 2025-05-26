On Hetzner (Ubuntu VERSION="24.04.1 LTS (Noble Numbat)") here's what I had to do:

- navigated to <https://console.hetzner.cloud/projects/4228251/servers/create>
- chose Hillsboro, OR as the location
- chose Ubuntu 24.04 as the image
- chose "Shared vCPU", x86 (Intel/AMD) as the type
  - within that, chose "CPX11" since that's the smallest and cheapest
- accepted the default SSH pub key that I'd already uploaded
- activated the firewall I've already created, named "ssh and https"
- clicked "Create and Buy Now"
- copied the IP address of the newly-created machine into the `Host hetz` stanza of `~/.ssh/config`, as the `hostname` entry

- `ssh root@hetz`, then

```shell
# # edit /etc/ssh/sshd_config
# # change `#PasswordAuthentication yes` to `PasswordAuthentication no`
# /etc/init.d/ssh restart

# adduser ubuntu # annoyingly interactive.
# exit
```

Now `ssh@hetz` and make sure it doesn't prompt for a password!!
If it doesn't (which is good), do `ssh root@hetz` again and continue ...

```shell
# apt update
# apt -y upgrade
# apt install -y htop docker.io
# usermod --append --groups sudo,docker ubuntu
# su - ubuntu
$ mkdir -vp ~/.ssh
$ cd .ssh
$ cat > authorized_keys # now paste your favorite ssh public key
$ exit
# curl -fsSL https://tailscale.com/install.sh | sh && tailscale up # there's some link to tailscale.com that you gotta click on to authorize the new machine
# tailscale serve --bg 9000

# fallocate -l 4g /mnt/4GiB.swap
# chmod 600 /mnt/4GiB.swap
# mkswap /mnt/4GiB.swap
# swapon /mnt/4GiB.swap
# echo '/mnt/4GiB.swap swap swap defaults 0 0' | tee -a /etc/fstab

# exit
```

- On my laptop:
  - update `~/.ssh/config` so that I can just "ssh hetz"
  - `docker context create hetz --docker "host=ssh://ubuntu@hetz"`
