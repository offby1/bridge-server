# Development prep

## Getting prerequistes &c

### Ubuntu "24.04.1 LTS (Noble Numbat)"

* git (`sudo apt install git`)
* just (`sudo apt install snapd && sudo snap install --edge --classic just`)
* docker & docker-compose
  - `sudo apt install docker-compose-v2`
  - `sudo usermod --append --groups docker $USER`
  - `exit`
  - start a new shell.  This gets you a login where you are a member of the "docker" group.
* jq (`sudo apt install jq`)
* uv
  - `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - `exec $SHELL`

### Ubuntu 26.04.1 LTS ("Resolute Raccoon"), inside a nested/sandboxed container

Same shape as 24.04 above, plus a few wrinkles specific to running inside a
container-within-a-container (no snap, no systemd login session, root fs is itself
overlayfs):

* git (`sudo apt install git`)
* just — apt's version (1.45.0 here) is too old for the `[continue]` attribute this
  justfile uses. Use the official installer instead of snap or apt:
  - `curl -fsSL https://just.systems/install.sh | sudo bash -s -- --to /usr/local/bin`
* docker, compose, and buildx
  - `sudo apt install docker.io docker-compose-v2 docker-buildx`
  - `sudo systemctl enable --now docker`
  - `sudo usermod --append --groups docker $USER`, then start a new *login* shell to
    pick up the group. If nothing in your setup gives you one (e.g. a long-lived
    non-interactive session), `sudo chmod 666 /var/run/docker.sock` works as a
    same-session stopgap.
  - If `docker compose build` dies with `failed to mount ... overlay ...`, the
    container's root filesystem is itself overlayfs, and BuildKit's default snapshotter
    can't do overlay-on-overlay. Fix: give buildx a builder that uses the `native`
    snapshotter instead —
    `docker buildx create --name sandbox-builder --driver docker-container --buildkitd-flags '--oci-worker-snapshotter=native' --use`
* jq (`sudo apt install jq`)
* a C/C++ toolchain, to compile the `endplay` extension the `bridge` library depends on
  - `sudo apt install build-essential cmake`
  - **without this, `uv sync`/`just uv-install` fails building `endplay`**, and the
    error is easy to misread as a Python-version problem: CMake's real complaint
    (`CMAKE_C_COMPILER not set`, `CMAKE_MAKE_PROGRAM not set`) is buried a couple of
    layers under a generic `setup.py build ... returned non-zero exit status 1`. It is
    *not* a 3.14-vs-3.12 issue — `endplay` builds fine under Python 3.14 too, once the
    compiler and cmake are actually present.
* uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
* Playwright's browser binary, which `uv sync` does not install
  - after `just uv-install`: `uv run playwright install chromium --with-deps`, or the
    UI tests fail with "Executable doesn't exist"

Two more things bit on first run, neither Ubuntu-version-specific:

* **`ensure-django-secret` leaves `SECRET_KEY` empty on any non-macOS box.** It sizes
  the secret file with `gstat` (GNU coreutils' `stat`, which is only called `gstat` on
  macOS, via `brew install coreutils`). Elsewhere `gstat` doesn't exist, the size check
  silently fails, and `touch` has already created an empty file — so the first test run
  dies with `SECRET_KEY setting must not be empty`. Workaround:
  `python3 -c 'import secrets; print(secrets.token_urlsafe(100))' > "$XDG_CONFIG_HOME/info.offby1.bridge/django_secret_key"`
  (or `~/.config/info.offby1.bridge/...` if `XDG_CONFIG_HOME` isn't set). The real fix
  is swapping `gstat` for something portable in the justfile.
* **The checkout directory must be named `server`.** `docker-compose.yaml`'s `django`
  build context is `context: ..` with `dockerfile: ./server/Dockerfile` — it assumes the
  repo lives in a directory literally named `server`, one level below where it reaches
  from. `git clone .../bridge-server.git` gives you `bridge-server/` by default, and
  `docker compose build` then fails with `lstat .../server: no such file or directory`.
  Rename the checkout to `server` before running `just dev`.

### Debian 12 ("bookworm")

* `sudo apt install git jq pipx`
* to finalize "pipx"
  - `pipx ensurepath`
  - `exec $SHELL`
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

### pre-commit
Optional but slick. `uv tool install pre-commit --with pre-commit-uv`

## Running it
- `just runme` runs the web server natively.  `DEPLOYMENT_ENVIRONMENT` will be `"development"`.  It still needs Docker for postgres, redis, and the change-notifier, and it starts all three; if the notifier won't start it warns and carries on, and you'll see stale pages until you reload.  It also runs `just ft` first, so a broken test suite stops you before the server comes up.

  😭😭 **on every Debian and Ubuntu box I've tried it on, this fails with ` Unable to find installation candidates for pyqt5-qt5 (5.15.15)`** 😭😭

  You might be able to work around this by somehow removing `python-lsp-server` but geez.

- `just dev` will bring up the docker-compose stack, which includes the web server, the bot, the tournament clock, the change-notifier, postgres and redis.  It conflicts with `just runme` since they both try to listen on the same port.
`DEPLOYMENT_ENVIRONMENT` will be `"development"`, since `just dev` passes `project.dev_settings`.  To make the laptop stack behave like a deployed one, pass prod settings: `DJANGO_SETTINGS_MODULE=project.prod_settings just dev` gets you `"staging"`, and adding `prod` to `COMPOSE_PROFILES` is what makes it `"production"`.

  (`just dcu` used to be the name of this; it now just prints "Use `just dev` now" and fails.)

- `just dev-monitoring` is `just dev` plus grafana, prometheus, the postgres exporter and pyroscope.

- `just prod` does what `just dev` does, plus:
  - it deploys to a docker context named "hetz-bridge", instead of locally.
    - you need to have prepared a host as per [this](docs/README.ubuntu-hetz.setup.md)
    - `docker context create hetz-bridge --docker "host=ssh://ubuntu@your-hetzner-host"`
    - no, of course it doesn't have to be Hetzner; that's just the one hosting provider for which I've written up detailed instructions.
  - it enables the "prod" profile, which includes "caddy", which is a TLS-doing reverse proxy *that gets TLS certificates for me automatically* 🎉  Caddy also carries the rate limits that shed a crawler flood before it reaches Daphne; see `docs/perf/crawler-repro.md`.
  - it enables the "monitoring" profile: grafana, prometheus, the postgres exporter, pyroscope
  - it insists that the working tree be clean and that you be on `main`

- `just beta` deploys to beta.bridge.offby1.info (docker context `hetz-bridge-beta`), and `just mini` to my mac mini over Tailscale.  Neither insists on a clean tree or on `main`, which is what makes them handy for trying a branch out.

## Using curl to examine event stream

- First "log in": `just curl-login`

- Now "tail" the stream: `just curl http://localhost:9000/events/player/json/1/` e.g.
