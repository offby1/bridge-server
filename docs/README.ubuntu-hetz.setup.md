On Hetzner (Ubuntu VERSION="24.04.1 LTS (Noble Numbat)") here's what I had to do (these steps ought to be automatable via [the hetzner cloud API CLI](https://github.com/hetznercloud/cli) or [the Python equivalent](https://github.com/hetznercloud/hcloud-python)):

- navigated to <https://console.hetzner.cloud/projects/4228251/servers/create>
- chose Hillsboro, OR as the location
- chose Ubuntu 24.04 as the image
- chose "Shared vCPU", x86 (Intel/AMD) as the type
  - within that, chose "CPX11" since that's the smallest and cheapest
- accepted the default SSH pub key that I'd already uploaded
- activated the firewall I've already created, named "ssh and https"
- clicked "Create and Buy Now"
- copied the IP address of the newly-created machine into the `Host hetz-prod` stanza of `~/.ssh/config`, as the `hostname` entry

- `ssh root@hetz-prod`, then (these manual steps are being obviated by [an ansible setup](https://gitlab.com/offby1/ansible-inventory)):

```shell
# vi /etc/ssh/sshd_config
# # change `#PasswordAuthentication yes` to `PasswordAuthentication no`
# # save
# /etc/init.d/ssh restart

# adduser ubuntu # annoyingly interactive.
# # use the password in my Google password manager (user eric.hanchrow.test@gmail.com; entry "hetzner.com", in the note).
# exit
```

Now `ssh hetz-prod` and make sure it just says "Permission denied", as opposed to prompting for a password!!
If that's all good, do `ssh root@hetz-prod` again and continue ...

```shell
# apt update
# apt -y upgrade
# apt install -y htop docker.io
# usermod --append --groups sudo,docker ubuntu
# cat > /etc/sudoers.d/99-no-password-for-ubuntu
  ubuntu ALL=(ALL) NOPASSWD:ALL
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
  - update `~/.ssh/config` so that I can just "ssh hetz-prod"
  - `docker context create hetz-prod --docker "host=ssh://ubuntu@hetz-prod"`
