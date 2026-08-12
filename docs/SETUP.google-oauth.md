# Google OAuth Setup Instructions

This guide walks you through enabling Google OAuth authentication for the Bridge server.

## Prerequisites

All the code is in place; see [`README.google-oauth.md`](README.google-oauth.md) for what
it consists of. All you need to do is get credentials from Google and put them where the
app looks for them.

## Step 1: Install Dependencies

```bash
just uv-install
```

This will install `django-allauth` and its dependencies.

## Step 2: Set Up Google OAuth Credentials

### 2.1 Create OAuth Credentials in Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to "APIs & Services" > "Credentials"
4. Click "Create Credentials" > "OAuth 2.0 Client ID"
5. Configure the OAuth consent screen if prompted:
   - User Type: External (for public access)
   - App name: Bridge Server
   - User support email: Your email
   - Developer contact: Your email
6. Create OAuth 2.0 Client ID:
   - Application type: **Web application**
   - Name: Bridge Server (or your preferred name)
   - Authorized redirect URIs:
     - Development: `http://localhost:9000/accounts/google/login/callback/`
     - Production: `https://bridge.offby1.info/accounts/google/login/callback/`
     - Beta: `https://beta.bridge.offby1.info/accounts/google/login/callback/`
7. Click "Create"
8. Copy the **Client ID** and **Client Secret** (you'll need these in the next step)

### 2.2 Store Credentials Locally

Create the directory and store your credentials:

```bash
mkdir -p "$HOME/Library/Application Support/info.offby1.bridge"
echo "YOUR_CLIENT_ID_HERE" > "$HOME/Library/Application Support/info.offby1.bridge/google_oauth_client_id"
echo "YOUR_CLIENT_SECRET_HERE" > "$HOME/Library/Application Support/info.offby1.bridge/google_oauth_client_secret"
```

Replace `YOUR_CLIENT_ID_HERE` and `YOUR_CLIENT_SECRET_HERE` with the actual values from Google Cloud Console.

**Security Note**: These files contain sensitive credentials. They are stored locally and not committed to git. The `.gitignore` should already exclude them.

## Step 3: Run migrations and the OAuth setup command

```bash
just setup-oauth
```

This migrates (so the `sites`, `account` and `socialaccount` tables exist) and then runs
the `setup_oauth` management command, which does two things you would otherwise do by hand:

- points `django.contrib.sites` at the right domain, chosen from
  `DEPLOYMENT_ENVIRONMENT` / `COMPOSE_PROFILES` / `HOSTNAME` — `localhost:9000` for local
  development, your `.ts.net` name if you're on Tailscale, `bridge.offby1.info` for
  production, `beta.bridge.offby1.info` for beta
- creates or updates the `SocialApp` row holding the client id and secret, and links it to
  that site

If the credential files from Step 2 are missing, it says so and skips the `SocialApp`; the
rest of the site works fine, just without a Google button.

Every deploy runs this for you, as the one-shot `django-oauth-setup` compose service, so
you only need it by hand when setting up locally or after changing credentials.

## Step 4: Start the Server

```bash
just runme
```

The server will start on `http://localhost:9000`

## Step 5: Test the OAuth Flow

### Test Traditional Authentication (Verify Backward Compatibility)

1. Visit `http://localhost:9000/signup/`
2. Create an account with username and password
3. Log out
4. Log back in with your credentials
5. ✅ Traditional auth should still work

### Test Google OAuth Signup

1. Visit `http://localhost:9000/signup/`
2. Click the **"Sign up with Google"** button
3. You'll be redirected to Google's login page
4. Sign in with your Google account
5. Grant permissions when prompted
6. You'll be redirected back to the Bridge server
7. You should see a **"Choose Your Username"** page
8. Enter a username (this will be visible to other players)
9. Click "Complete Sign Up"
10. ✅ You should be logged in with your chosen username

### Test Google OAuth Login

1. Log out
2. Visit `http://localhost:9000/accounts/login/`
3. Click the **"Sign in with Google"** button
4. You'll be redirected to Google
5. Select your account (or sign in if needed)
6. ✅ You should be logged in immediately (no username selection this time)

### Verify Email Privacy

1. While logged in with a Google account, visit your player page
2. ✅ Your chosen username should be visible, and there should be no email address anywhere

We don't merely hide the address: we never ask Google for it. The requested scope is
`profile` only, so there is no email address in the database at all.

## Troubleshooting

### "Redirect URI mismatch" error

- **Problem**: Google shows an error about redirect URI mismatch
- **Solution**: Check that the redirect URI in Google Cloud Console exactly matches your server URL, including the port (`:9000` for local development)

### "Site matching query does not exist"

- **Problem**: Django complains about missing Site object
- **Solution**: `just setup-oauth` (Step 3)

### Google OAuth button fails when clicked

The button is rendered unconditionally by `signup.html` and `registration/login.html`, so
its presence tells you nothing about whether OAuth is configured. If clicking it errors:

  1. The credential files may be missing — check `just setup-oauth`'s output, which says so
     explicitly
  2. There may be no `SocialApp` row, for the same reason
  3. The Site domain may not match the host you're browsing (see the next entry)

### OAuth flow starts but fails with 500 error

- **Problem**: After clicking "Sign in with Google", the flow starts but fails
- **Solution**: Check server logs for details. Running natively, they're on your terminal;
  in Docker, `docker compose logs django --tail=100`, or `just dump` to write them to a
  timestamped file.
- Common issues:
  - OAuth credentials not loaded (check the credential files)
  - Site not configured (run `just setup-oauth`)

### Username already taken

- **Problem**: After OAuth, username selection fails with "username already taken"
- **Solution**: Choose a different username - usernames must be unique

## Production Deployment

See [`DEPLOY.google-oauth.md`](DEPLOY.google-oauth.md). The short version: the credentials
stay on your laptop, `just prod` reads them and passes them to the remote host as Docker
secrets, and the `django-oauth-setup` service configures the `SocialApp` and the Site
domain there. You don't copy anything to the server, and you don't touch the Django shell.

Make sure Google Cloud Console has the production redirect URI:
`https://bridge.offby1.info/accounts/google/login/callback/`.

## Security Notes

- OAuth credentials are sensitive - never commit them to git
- The `GOOGLE_OAUTH_CLIENT_SECRET` should be treated like a password
- The implementation uses HTTPS in production (enforced by existing settings)
- We never request the user's email address from Google, so there is none to expose
- Users choose custom usernames to maintain privacy

## Additional Resources

- [django-allauth Documentation](https://docs.allauth.org/)
- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- Implementation details: See `docs/README.google-oauth.md`
