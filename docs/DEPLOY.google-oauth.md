# Deploying Google OAuth to Production

This guide explains how to deploy your Google OAuth credentials to production. The credentials stay on your **local machine** and are securely transmitted to the production host during deployment via Docker secrets.

## Prerequisites

1. You've created OAuth credentials in [Google Cloud Console](https://console.cloud.google.com/)
   - Note: the URL to this project is <https://console.cloud.google.com/auth/clients/717889496624-mabeh1tfribiocm11uu2h7ufnrimijgj.apps.googleusercontent.com>
2. You've configured the OAuth consent screen
3. You've added authorized redirect URIs:
   - `https://bridge.offby1.info/accounts/google/login/callback/` (production)
   - `https://beta.bridge.offby1.info/accounts/google/login/callback/` (beta)
   - `http://localhost:9000/accounts/google/login/callback/` (development)
4. Your credentials are saved locally at:
   - `~/Library/Application Support/info.offby1.bridge/google_oauth_client_id`
   - `~/Library/Application Support/info.offby1.bridge/google_oauth_client_secret`

## How It Works

The deployment follows the same pattern as your existing Django secrets:

1. `just prod` reads credential files from **your local machine**
2. Exports them as environment variables
3. Docker Compose (via SSH context) sends these to the production host
4. Docker creates secrets from the environment variables
5. Django container reads them from `/run/secrets/`

**Important:** Credentials never need to be manually copied to the production host. They're transmitted securely during deployment.

## Step 1: Nothing, usually

The justfile already exports `GOOGLE_OAUTH_CLIENT_ID_FILE` and
`GOOGLE_OAUTH_CLIENT_SECRET_FILE`, pointing at
`{{ config_directory() }}/info.offby1.bridge/`. So as long as your credential files are in
the standard place (see the Prerequisites above), there is nothing to set up in your shell
profile. Setting those variables yourself still works, and overrides the default.

## Step 2: Deploy

Now deploy normally using:

```bash
just prod
```

The `prod` recipe will:
1. Read the credential files from **your local machine**
2. Export them as environment variables
3. Docker Compose sends them to the production host and injects them as secrets into the Django container
4. Django reads them at `/run/secrets/google_oauth_client_id` and `/run/secrets/google_oauth_client_secret`, because the compose file sets `GOOGLE_OAUTH_CLIENT_ID_FILE` and `GOOGLE_OAUTH_CLIENT_SECRET_FILE` to those paths
5. The one-shot `django-oauth-setup` service runs `setup_oauth`, which writes the `SocialApp` row and sets the Site domain, before the new `django` container starts

## Step 3: Verify Deployment

After deployment, check that OAuth is working:

1. Visit `https://bridge.offby1.info/accounts/login/`
2. Click the "Sign in with Google" button and verify you can complete the OAuth flow.
   (The button is there whether or not OAuth is configured, so only completing the flow
   proves anything.)

Check Django logs for any OAuth-related errors:
```bash
docker context use hetz-bridge
docker compose logs django | grep -i oauth
```

## Troubleshooting

### "Sign in with Google" doesn't work

The button itself is unconditional, so seeing it tells you nothing. Check whether the
credentials actually reached the container:
```bash
docker context use hetz-bridge
docker compose exec django sh -c 'ls -la /run/secrets/google_oauth_*'
```

If files are missing, verify on your **local machine** (where you run `just prod`):
1. Environment variables are set: `echo $GOOGLE_OAUTH_CLIENT_ID_FILE`
2. Files exist at those paths: `ls -la "$GOOGLE_OAUTH_CLIENT_ID_FILE"`
3. Files contain the credentials (not empty): `cat "$GOOGLE_OAUTH_CLIENT_ID_FILE"`

### OAuth redirect URI mismatch

Error: `Error 400: redirect_uri_mismatch`

Solution: In Google Cloud Console, ensure you've added:
```
https://bridge.offby1.info/accounts/google/login/callback/
```

Note: Must use `https://` (not `http://`) and must match exactly (no trailing slashes elsewhere).

### Site domain not configured

`setup_oauth` sets this on every deploy, from `DEPLOYMENT_ENVIRONMENT` and
`COMPOSE_PROFILES`. If OAuth redirects to the wrong domain, look at what that command
printed:

```bash
docker context use hetz-bridge
docker compose logs django-oauth-setup
```

To re-run it against the deployed stack:

```bash
docker compose run --rm django-oauth-setup
```

## Security Notes

1. **Never commit credentials to git** - They're loaded from files outside the repo
2. **Credentials stay local** - Files remain on your local machine; they're transmitted securely during deployment via SSH
3. **File permissions** - Local credential files should be `chmod 600` (owner read/write only)
4. **Backup** - Keep a secure backup of your OAuth credentials (password manager, etc.)
5. **Rotation** - If credentials are compromised, regenerate them in Google Cloud Console, update your local files, and redeploy

## Beta Environment

For beta deployment:
1. Ensure the same environment variables are set on your local machine (they point to the same local credential files)
2. Run `just beta` instead of `just prod`

The beta environment will use the same OAuth app (same credentials), but ensure the beta redirect URI is registered:
```
https://beta.bridge.offby1.info/accounts/google/login/callback/
```

## Optional: Disabling OAuth

Unsetting the environment variables won't do it, because the justfile exports them itself.
To disable OAuth, move the credential files aside:

```bash
mv "$GOOGLE_OAUTH_CLIENT_ID_FILE" "$GOOGLE_OAUTH_CLIENT_ID_FILE.disabled"
mv "$GOOGLE_OAUTH_CLIENT_SECRET_FILE" "$GOOGLE_OAUTH_CLIENT_SECRET_FILE.disabled"
```

then redeploy with `just prod`. `_deploy` tolerates the files being missing (it exports an
empty string), `base_settings.py` leaves both values `None`, and `setup_oauth` warns and
skips creating the `SocialApp`.

Note that this leaves the "Sign in with Google" button *visible*: `signup.html` and
`registration/login.html` link to `{% url 'google_login' %}` unconditionally. With no
`SocialApp` in the database, clicking it fails. Hiding the button too would mean gating
those two templates on whether a Google `SocialApp` exists; nobody has needed that yet.

Or, to break it from the other end: remove the redirect URIs from Google Cloud Console.

Username-and-password login is unaffected either way.
