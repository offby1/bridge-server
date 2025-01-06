# Wassup homies

## Getting prerequistes &c

For Ubuntu "24.10 (Oracular Oriole)", this gets everything except "just" (for which, see the next section):
- `sudo apt install git python3-poetry docker-compose-v2 jq`
- ... somehow add your userID to the "docker" group, then log out and log back in (hint: `sudo vigr`)
- `(d=~/.config/info.offby1.bridge; mkdir -vp ${d} && echo "yadda yadda whatever" > "${d}/django_secret_key")`
- `sudo apt install snapd`
- `sudo snap install --edge --classic just`

### just
If the "snap" stuff above didn't work:
- `curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin`
- `PATH=$PATH:$HOME/.local/bin`

Yeah, I hate `curl | sh` too, but there doesn't seem to be any other foolproof way.
Take a look at <https://just.systems/man/en/chapter_4.html> for other options.

### pipx
- `sudo apt install pipx`

### pre-commit
Optional but slick. `pipx install pre-commit`

### poetry
- `pipx install poetry`

## Running it
- `just runme` will start just the web server.  `DEPLOYMENT_ENVIRONMENT` will be `"development"`.
- `just dcu` will bring up the docker-compose stack, which includes the web server, bot, and who knows what-all else.  It conflicts with `just runme` since they both try to listen on the same port.
`DEPLOYMENT_ENVIRONMENT` will be `"staging"` on the laptop, and `"production"` elsewhere.  When running on the laptop, you can fool it into thinking it's production by invoking e.g. `DJANGO_SETTINGS_MODULE=project.prod_settings HOSTNAME=yeah.im.production.trustme just dcu`
