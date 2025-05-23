# Development prep

## Getting prerequistes &c

### Ubuntu "24.04.1 LTS (Noble Numbat)"

* git (`sudo apt install git`)
* just (`sudo apt install snapd && sudo snap install --edge --classic just`)
* docker & docker-compose (`sudo apt install docker-compose-v2`)
  - `sudo usermod --append --groups docker $USER`
  - `exit`
  - start a new shell.  This gets you a login where you are a member of the "docker" group.
* jq (`sudo apt install jq`)
* pipx (`sudo apt install pipx`)
  - `~/.local/bin/pipx ensurepath`
  - `exec $SHELL`
* poetry (`pipx install poetry`) [1]

[1] In theory, you could install poetry through apt; but the version you'd get isn't new enough.

### Debian 12 ("bookworm")

* `sudo apt install git jq pipx`
* to finalize "pipx"
  - `pipx ensurepath`
  - `exec $SHELL`
* poetry (`pipx install poetry`) [1]
* "just"
  - `curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to $HOME/.local/bin`
* docker and friends
  - `curl -fsSL https://get.docker.com -o get-docker.sh`
  - `sudo sh ./get-docker.sh --dry-run`
  - once you're happy
  - `sudo sh ./get-docker.sh`
  - `sudo usermod --append --groups docker $USER`
  - `exit`
  - start a new shell.  This gets you a login where you are a member of the "docker" group.

### Debian 11 ("bullseye")

Seems too old to be worthwhile; in particular, it ships with python3.9 and it's not obvious that you can easily install a newer python.  ("Building from source" does not count as "easy".)

### MacOS (15.2 (24C101) "Sequoia")

The below is from memory; it's hard to get a fresh MacOS installation to test it on.

* git is preinstalled, yay
* `brew install just`
* I use [orbstack](https://orbstack.dev/) instad of Docker Desktop, although the latter works fine
* `brew install jq`
* python from <https://www.python.org/downloads/macos/>
* pipx via `/Library/Frameworks/Python.framework/Versions/Current/bin/python3 -m pip install pipx`
* not strictly needed, but handy for keeping python up to date: `pipx install mopup`
* `pipx install poetry`

### pre-commit
Optional but slick. `pipx install pre-commit`

## Running it
- `just runme` will start just the web server.  `DEPLOYMENT_ENVIRONMENT` will be `"development"`.

  😭😭 **on every Debian and Ubuntu box I've tried it on, this fails with ` Unable to find installation candidates for pyqt5-qt5 (5.15.15)`** 😭😭

  You can work around this by doing `poetry remove python-lsp-server` but geez.

- `just dcu` will bring up the docker-compose stack, which includes the web server and bots (and postgres).  It conflicts with `just runme` since they both try to listen on the same port.
`DEPLOYMENT_ENVIRONMENT` will be `"staging"` on the laptop, and `"production"` elsewhere.  When running on the laptop, you can fool it into thinking it's production by invoking e.g. `DJANGO_SETTINGS_MODULE=project.prod_settings HOSTNAME=yeah.im.production.trustme just dcu`

- `just prod` does what `just dcu` does, plus:
  - it deploys to a docker context named "ls", instead of locally.  This won't work for you unless you have a host accessible via `ssh ls`. Mine is a server that has a slick-looking domain name (`bridge.offby1.info`).
  - it enables the "prod" profile, which includes "caddy", which is a TLS-doing reverse proxy *that gets TLS certificates for me automatically* 🎉

## Using curl to examine event stream

- First "log in"
  `curl --cookie cook --cookie-jar cook -u 'bob:.'  https://django.server.orb.local/three-way-login/`

- Now "tail" the stream
  `curl  --cookie cook --cookie-jar cook   https://django.server.orb.local/events/hand/1/`
