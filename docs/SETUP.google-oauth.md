# Google OAuth Setup Instructions

This guide walks you through enabling Google OAuth authentication for the Bridge server.

## Prerequisites

All code changes are already implemented. You just need to configure Google OAuth credentials and set up the Django Sites framework.

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

## Step 3: Configure Django Sites Framework

The `django.contrib.sites` framework needs to know your domain name.

Start the Django shell:
```bash
just shell
```

Then run these commands in the shell:
```python
from django.contrib.sites.models import Site

# Get the current site (created by migrations with id=1)
site = Site.objects.get_current()

# Configure for your environment
# Development:
site.domain = "localhost:9000"
site.name = "Bridge Server (Development)"

# OR for Production:
# site.domain = "bridge.offby1.info"
# site.name = "Bridge Server"

# OR for Beta:
# site.domain = "beta.bridge.offby1.info"
# site.name = "Bridge Server (Beta)"

# Save the changes
site.save()

# Verify
print(f"Site configured: {site.domain} ({site.name})")
exit()
```

## Step 4: Run Migrations

Ensure all database tables are created:

```bash
just migrate
```

You should see that the `sites`, `account`, and `socialaccount` migrations have been applied.

## Step 5: Start the Server

```bash
just runme
```

The server will start on `http://localhost:9000`

## Step 6: Test the OAuth Flow

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
2. ✅ Your chosen username should be visible, but NOT your email address
3. Your email is stored in the database but not displayed publicly

## Troubleshooting

### "Redirect URI mismatch" error

- **Problem**: Google shows an error about redirect URI mismatch
- **Solution**: Check that the redirect URI in Google Cloud Console exactly matches your server URL, including the port (`:9000` for local development)

### "Site matching query does not exist"

- **Problem**: Django complains about missing Site object
- **Solution**: Run the Django shell commands from Step 3 to configure the site

### Google OAuth button doesn't appear

- **Problem**: The "Sign in with Google" button is missing
- **Possible causes**:
  1. OAuth credentials not configured (check the files exist)
  2. Browser cache - try hard refresh (Cmd+Shift+R)
  3. Check console for JavaScript errors

### OAuth flow starts but fails with 500 error

- **Problem**: After clicking "Sign in with Google", the flow starts but fails
- **Solution**: Check server logs for details:
  ```bash
  just logs
  ```
- Common issues:
  - OAuth credentials not loaded (check the credential files)
  - Site not configured (run Step 3 commands)

### Username already taken

- **Problem**: After OAuth, username selection fails with "username already taken"
- **Solution**: Choose a different username - usernames must be unique

## Production Deployment

For production deployment:

1. **Set OAuth credentials as environment variables** (recommended) or create credential files on the production server:
   ```bash
   export GOOGLE_OAUTH_CLIENT_ID_FILE="/path/to/google_oauth_client_id"
   export GOOGLE_OAUTH_CLIENT_SECRET_FILE="/path/to/google_oauth_client_secret"
   ```

2. **Update Google Cloud Console** with production redirect URI:
   - Add `https://bridge.offby1.info/accounts/google/login/callback/`

3. **Configure the Site for production**:
   ```python
   site.domain = "bridge.offby1.info"
   site.name = "Bridge Server"
   site.save()
   ```

4. **Deploy**:
   ```bash
   just prod
   ```

## Security Notes

- OAuth credentials are sensitive - never commit them to git
- The `GOOGLE_OAUTH_CLIENT_SECRET` should be treated like a password
- The implementation uses HTTPS in production (enforced by existing settings)
- Email addresses from Google are stored but not displayed publicly
- Users choose custom usernames to maintain privacy

## Additional Resources

- [django-allauth Documentation](https://docs.allauth.org/)
- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- Implementation details: See `docs/README.google-oauth.md`
