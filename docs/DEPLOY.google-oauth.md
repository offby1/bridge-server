# Deploying Google OAuth to Production

This guide explains how to securely deploy your Google OAuth credentials to the production server.

## Prerequisites

1. You've created OAuth credentials in [Google Cloud Console](https://console.cloud.google.com/)
2. You've configured the OAuth consent screen
3. You've added authorized redirect URIs:
   - `https://bridge.offby1.info/accounts/google/login/callback/` (production)
   - `https://beta.bridge.offby1.info/accounts/google/login/callback/` (beta)
   - `http://localhost:9000/accounts/google/login/callback/` (development)

## Step 1: Copy Credentials to Production Host

From your local machine, securely copy the credentials using `scp`:

```bash
# Copy client ID
scp ~/Library/Application\ Support/info.offby1.bridge/google_oauth_client_id \
    ubuntu@YOUR_PROD_IP:~/google_oauth_client_id

# Copy client secret
scp ~/Library/Application\ Support/info.offby1.bridge/google_oauth_client_secret \
    ubuntu@YOUR_PROD_IP:~/google_oauth_client_secret
```

Replace `YOUR_PROD_IP` with your actual production server IP or hostname.

## Step 2: Place Credentials Securely on Host

SSH to your production server and move the credentials to a secure location:

```bash
ssh ubuntu@YOUR_PROD_IP

# Create secure directory for secrets (if it doesn't exist)
sudo mkdir -p /opt/bridge/secrets
sudo chown ubuntu:ubuntu /opt/bridge/secrets
chmod 700 /opt/bridge/secrets

# Move credentials there
mv ~/google_oauth_client_id /opt/bridge/secrets/
mv ~/google_oauth_client_secret /opt/bridge/secrets/

# Set restrictive permissions (only owner can read)
chmod 600 /opt/bridge/secrets/google_oauth_*

# Verify permissions
ls -la /opt/bridge/secrets/
```

Expected output:
```
drwx------ 2 ubuntu ubuntu 4096 ... .
drwxr-xr-x 3 ubuntu ubuntu 4096 ... ..
-rw------- 1 ubuntu ubuntu   72 ... google_oauth_client_id
-rw------- 1 ubuntu ubuntu   40 ... google_oauth_client_secret
```

## Step 3: Configure Environment Variables

On your **local machine** (where you run `just prod`), ensure these environment variables are set before deployment:

```bash
# Add to your shell profile (~/.zshrc, ~/.bashrc, or ~/.profile)
export GOOGLE_OAUTH_CLIENT_ID_FILE="/opt/bridge/secrets/google_oauth_client_id"
export GOOGLE_OAUTH_CLIENT_SECRET_FILE="/opt/bridge/secrets/google_oauth_client_secret"
```

Reload your shell:
```bash
source ~/.zshrc  # or source ~/.bashrc
```

## Step 4: Deploy

Now deploy normally using:

```bash
just prod
```

The `prod` recipe will:
1. Read the credential files from the production host paths you specified
2. Export them as environment variables
3. Docker Compose will inject them as secrets into the Django container
4. Django will read them at `/run/secrets/google_oauth_client_id` and `/run/secrets/google_oauth_client_secret`

## Step 5: Verify Deployment

After deployment, check that OAuth is working:

1. Visit `https://bridge.offby1.info/accounts/login/`
2. You should see the "Sign in with Google" button
3. Click it and verify you can complete the OAuth flow

Check Django logs for any OAuth-related errors:
```bash
docker context use hetz-bridge
docker compose logs django | grep -i oauth
```

## Troubleshooting

### "Sign in with Google" button not visible

Check if credentials are loaded in the container:
```bash
docker context use hetz-bridge
docker compose exec django sh -c 'ls -la /run/secrets/google_oauth_*'
```

If files are missing, verify:
1. Environment variables are set on your local machine
2. Files exist at the paths specified in the environment variables
3. You have SSH access to read the files on the remote host

### OAuth redirect URI mismatch

Error: `Error 400: redirect_uri_mismatch`

Solution: In Google Cloud Console, ensure you've added:
```
https://bridge.offby1.info/accounts/google/login/callback/
```

Note: Must use `https://` (not `http://`) and must match exactly (no trailing slashes elsewhere).

### Site domain not configured

If OAuth redirects to the wrong domain, update the Django Sites framework:

```bash
docker context use hetz-bridge
docker compose exec django uv run python manage.py shell
```

In the shell:
```python
from django.contrib.sites.models import Site
site = Site.objects.get_current()
site.domain = "bridge.offby1.info"
site.name = "Bridge Server"
site.save()
```

## Security Notes

1. **Never commit credentials to git** - They're loaded from files outside the repo
2. **File permissions** - Credentials should be `chmod 600` (owner read/write only)
3. **Directory permissions** - Secret directory should be `chmod 700` (owner access only)
4. **Backup** - Keep a secure backup of your OAuth credentials (password manager, etc.)
5. **Rotation** - If credentials are compromised, regenerate them in Google Cloud Console and redeploy

## Beta Environment

For beta deployment, use the same steps but:
1. Use beta server IP/hostname
2. Ensure credentials are at the same paths on the beta host
3. Run `just beta` instead of `just prod`

The beta environment will use the same OAuth app, but ensure the beta redirect URI is registered:
```
https://beta.bridge.offby1.info/accounts/google/login/callback/
```

## Optional: Disabling OAuth

If you want to temporarily disable OAuth without removing the credentials:

1. Remove the redirect URIs from Google Cloud Console (OAuth will fail gracefully)
2. Or, delete the credential files from `/opt/bridge/secrets/` on the host

The Django app is designed to work without OAuth credentials - the "Sign in with Google" button simply won't appear if credentials aren't configured.
