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
* uv (TBD)
* poetry (`uv tool install poetry`) [1]

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
* uv via `brew install uv`
* not strictly needed, but handy for keeping python up to date: `uv tool install mopup`
* `uv tool install poetry`

### pre-commit
Optional but slick. `uv tool install pre-commit --with pre-commit-uv`

## Running it
- `just runme` will start just the web server.  `DEPLOYMENT_ENVIRONMENT` will be `"development"`.

  😭😭 **on every Debian and Ubuntu box I've tried it on, this fails with ` Unable to find installation candidates for pyqt5-qt5 (5.15.15)`** 😭😭

  You can work around this by doing `poetry remove python-lsp-server` but geez.

- `just dcu` will bring up the docker-compose stack, which includes the web server and bots (and postgres).  It conflicts with `just runme` since they both try to listen on the same port.
`DEPLOYMENT_ENVIRONMENT` will be `"staging"` on the laptop, and `"production"` elsewhere.  When running on the laptop, you can fool it into thinking it's production by invoking e.g. `DJANGO_SETTINGS_MODULE=project.prod_settings HOSTNAME=yeah.im.production.trustme just dcu`

- `just prod` does what `just dcu` does, plus:
  - it deploys to a docker context named "hetz-prod", instead of locally.
    - you need to have prepared a host as per [this](docs/README.ubuntu-hetz.setup.md)
    - `docker context create hetz-prod --docker "host=ssh://ubuntu@your-hetzner-host"`
    - no, of course it doesn't have to be Hetzner; that's just the one hosting provider for which I've written up detailed instructions.

  - it enables the "prod" profile, which includes "caddy", which is a TLS-doing reverse proxy *that gets TLS certificates for me automatically* 🎉

## Using curl to examine event stream

- First "log in": `just curl-login`

- Now "tail" the stream: `just curl https://django.server.orb.local/events/hand/1/` e.g.
