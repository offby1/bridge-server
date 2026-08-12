# Google OAuth: how it works here

**Status: built and deployed.** This document describes the code as it stands. It used to
be an implementation plan, and the plan differed from what shipped in several places, so
don't take an old copy as gospel — the settings names in particular changed.

For how to *set it up* locally, see [`SETUP.google-oauth.md`](SETUP.google-oauth.md); for
deployment, [`DEPLOY.google-oauth.md`](DEPLOY.google-oauth.md).

## What it does

Users can sign up and log in with a Google account, via `django-allauth`. The requirement
that drove the design, from [`desiderata.md`](../desiderata.md): an OAuth user still picks
a short username, so signing in with Google does not expose an email address to everyone
who looks at the site.

We go further than "don't display the email": **we never ask Google for it.** The
requested scope is `profile` only, `SOCIALACCOUNT_QUERY_EMAIL` is `False`, and
`ACCOUNT_SIGNUP_FIELDS` omits email, so there is no email address in the database to leak.
That also means no email verification, which suits us — see the comment on `MAILERS` in
`base_settings.py` for why we send no mail at all.

Whether a player signed in with Google is not entirely invisible: `Player.is_oauth_verified`
is true for such a player, and `base_player_detail.html` and the chat gate
(`readers.get_chat_disabled_explanation`) use it — private chat requires both parties to be
OAuth-verified.

## The pieces

| Where | What |
|---|---|
| `project/project/base_settings.py` | allauth apps, `AUTHENTICATION_BACKENDS`, `SITE_ID`, the allauth settings, and `SOCIALACCOUNT_PROVIDERS` |
| `project/project/urls.py` | `path("accounts/", include("allauth.urls"))`, before `django.contrib.auth.urls` |
| `project/app/forms.py` | `SocialSignupForm` — asks for a username and nothing else |
| `project/app/adapters.py` | `CustomSocialAccountAdapter` — refuses auto-signup so the username page always appears, and creates the `Player` row in `save_user` |
| `project/app/templates/registration/login.html`, `signup.html` | the "Sign in / Sign up with Google" buttons, linking to `{% url 'google_login' %}` |
| `project/app/templates/socialaccount/signup.html` | the "choose your username" page |
| `project/app/management/commands/setup_oauth.py` | creates or updates the `SocialApp` row and points `django.contrib.sites` at the right domain |
| `project/app/test_oauth.py` | the tests |

## Two things worth knowing

**The credentials live in the database, not in settings.** `SOCIALACCOUNT_PROVIDERS` in
`base_settings.py` deliberately has no `APP` key: defining one creates an in-memory
`SocialApp` *alongside* the one in the database, and allauth then raises
`MultipleObjectsReturned`. The `setup_oauth` management command is what writes the database
row, from `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`, and it runs on every
deploy as the one-shot `django-oauth-setup` compose service. `just setup-oauth` runs it by
hand.

**Nothing breaks without credentials.** `base_settings.py` catches the missing-file case
and leaves both values `None`; `setup_oauth` then warns and skips the `SocialApp` entirely.
Username-and-password login is untouched, since `ModelBackend` is still first in
`AUTHENTICATION_BACKENDS`.

## Google Cloud Console

The OAuth client lives in the `oauth-mojo-for-bridge-server` project:
<https://console.cloud.google.com/apis/credentials?project=oauth-mojo-for-bridge-server>

Registered redirect URIs:

- `http://localhost:9000/accounts/google/login/callback/` (development)
- `https://bridge.offby1.info/accounts/google/login/callback/` (production)
- `https://beta.bridge.offby1.info/accounts/google/login/callback/` (beta)
