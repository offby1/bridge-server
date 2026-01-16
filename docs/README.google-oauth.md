# Google OAuth Implementation Plan

## Overview

Add Google OAuth authentication using `django-allauth` to allow users to sign up and log in with their Google accounts. Key requirement: OAuth users must choose a custom username (not expose their email address publicly).

## Requirements (from desiderata.md)

1. Add "Sign in with Google" button to `/accounts/login/` and `/signup/` pages
2. OAuth users choose a custom username during signup (email stays private)
3. Keep existing username/password authentication working
4. Conventional experience like other websites

## Implementation Steps

### 1. Install django-allauth

**File: `pyproject.toml`**
- Add `"django-allauth[socialaccount]>=65.4.0,<66"` to dependencies array (around line 42)
- Run: `just uv-install`

### 2. Configure Settings

**File: `project/project/base_settings.py`**

Add Google OAuth credentials helper (after line 65):
```python
GOOGLE_OAUTH_CLIENT_ID = from_env_var_file(
    "GOOGLE_OAUTH_CLIENT_ID_FILE",
    "/Users/not-workme/Library/Application Support/info.offby1.bridge/google_oauth_client_id",
)
GOOGLE_OAUTH_CLIENT_SECRET = from_env_var_file(
    "GOOGLE_OAUTH_CLIENT_SECRET_FILE",
    "/Users/not-workme/Library/Application Support/info.offby1.bridge/google_oauth_client_secret",
)
```

Update `INSTALLED_APPS` (around line 79):
```python
INSTALLED_APPS = [
    # ... existing apps ...
    "django.contrib.sites",  # ADD - required by allauth
    # ... existing apps ...
    "allauth",  # ADD
    "allauth.account",  # ADD
    "allauth.socialaccount",  # ADD
    "allauth.socialaccount.providers.google",  # ADD
    "app",
]
```

Add after INSTALLED_APPS (around line 99):
```python
SITE_ID = 1  # Required by django.contrib.sites
```

Update `MIDDLEWARE` (after line 137, add after AuthenticationMiddleware):
```python
"allauth.account.middleware.AccountMiddleware",
```

Add after LOGIN_REDIRECT_URL (around line 157):
```python
# Authentication backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # Keep for traditional login
    "allauth.account.auth_backends.AuthenticationBackend",  # Add for allauth
]

# Allauth configuration
ACCOUNT_AUTHENTICATION_METHOD = "username"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_USERNAME_REQUIRED = True
ACCOUNT_SIGNUP_FORM_CLASS = "app.forms.AllauthSignupForm"
SOCIALACCOUNT_AUTO_SIGNUP = False  # Force username selection
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_STORE_TOKENS = False  # Don't need tokens
SOCIALACCOUNT_ADAPTER = "app.adapters.CustomSocialAccountAdapter"

# Google OAuth settings
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APP": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "key": "",
        }
    }
}
```

### 3. Update URL Configuration

**File: `project/project/urls.py`**

Add allauth URLs BEFORE django.contrib.auth.urls (around line 39):
```python
path("accounts/", include("allauth.urls")),  # ADD THIS - must come before django.contrib.auth.urls
path("accounts/", include("django.contrib.auth.urls")),  # Existing
```

### 4. Create Custom Forms

**File: `project/app/forms.py`**

Add after existing LoginForm (around line 38):
```python
class AllauthSignupForm(forms.Form):
    """
    Custom signup form for social account users (Google OAuth).
    Allows users to choose a custom username when signing up with Google.
    """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            "autofocus": True,
            "placeholder": "Choose a username",
            "class": "form-control"
        }),
        help_text="This username will be visible to other players. Your email remains private."
    )

    def signup(self, request, user):
        """Called by allauth to complete the signup process."""
        user.username = self.cleaned_data["username"]
        user.save()
        Player.objects.create(user=user)
```

### 5. Create Custom Adapter

**New File: `project/app/adapters.py`**
```python
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter to handle social account signup flow.
    Forces username selection for OAuth users.
    """

    def is_auto_signup_allowed(self, request, sociallogin):
        """Return False to force username selection page."""
        return False

    def populate_user(self, request, sociallogin, data):
        """Populate user from social data. Username set by form."""
        user = super().populate_user(request, sociallogin, data)
        return user
```

### 6. Update Templates

**File: `project/app/templates/registration/login.html`**

Add after the login form button (before closing form tag, around line 31):
```html
</form>

<!-- ADD THIS SECTION -->
<div class="text-center my-3">
    <span class="text-muted">- OR -</span>
</div>

<a href="{% url 'google_login' %}" class="btn btn-outline-primary w-100">
    <svg width="18" height="18" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" style="margin-right: 8px;">
        <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
        <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
        <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
        <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
    </svg>
    Sign in with Google
</a>
```

**File: `project/app/templates/signup.html`**

Add similar Google button after the signup form button.

**New File: `project/app/templates/socialaccount/signup.html`**
```html
{% extends "base.html" %}

{% block content %}
<div class="container mt-4">
    <div class="row justify-content-center">
        <div class="col-md-6 col-lg-4">
            <h2 class="mb-4">Choose Your Username</h2>

            <p class="text-muted">
                You're signing up with your Google account.
                Please choose a username that will be visible to other players.
                Your email address will remain private.
            </p>

            <form method="post">
                {% csrf_token %}

                {% if form.errors %}
                    <div class="alert alert-danger">{{ form.errors }}</div>
                {% endif %}

                <div class="mb-3">
                    {{ form.username.label_tag }}
                    {{ form.username }}
                    {% if form.username.help_text %}
                        <div class="form-text">{{ form.username.help_text }}</div>
                    {% endif %}
                </div>

                <button type="submit" class="btn btn-primary w-100">Complete Sign Up</button>
            </form>
        </div>
    </div>
</div>
{% endblock %}
```

### 7. Set Up Google OAuth Credentials

1. **Google Cloud Console**:
   - Go to https://console.cloud.google.com/
   - Create OAuth 2.0 Client ID (Web application)
   - Authorized redirect URIs:
     - `http://localhost:9000/accounts/google/login/callback/`
     - `https://bridge.offby1.info/accounts/google/login/callback/`
   - Save Client ID and Client Secret

2. **Store Credentials Locally**:
   ```bash
   mkdir -p "$HOME/Library/Application Support/info.offby1.bridge"
   echo "YOUR_CLIENT_ID" > "$HOME/Library/Application Support/info.offby1.bridge/google_oauth_client_id"
   echo "YOUR_CLIENT_SECRET" > "$HOME/Library/Application Support/info.offby1.bridge/google_oauth_client_secret"
   ```

### 8. Run Migrations and Setup

```bash
just migrate  # Creates allauth tables
just runme    # Start server
```

In Django shell (or create management command):
```python
from django.contrib.sites.models import Site
site = Site.objects.get_current()
site.domain = "localhost:9000"
site.name = "Bridge Server (Development)"
site.save()
```

### 9. Update Justfile (Optional)

Add recipe to manage OAuth secrets:
```just
ensure-google-oauth-secrets:
    # Script to prompt for and save OAuth credentials
```

Update `runme` recipe to include OAuth setup.

## Critical Files Modified

1. `pyproject.toml` - Add django-allauth dependency
2. `project/project/base_settings.py` - Allauth configuration (INSTALLED_APPS, AUTHENTICATION_BACKENDS, allauth settings)
3. `project/project/urls.py` - Include allauth URLs
4. `project/app/forms.py` - Add AllauthSignupForm
5. `project/app/adapters.py` - NEW FILE - CustomSocialAccountAdapter
6. `project/app/templates/registration/login.html` - Add Google button
7. `project/app/templates/signup.html` - Add Google button
8. `project/app/templates/socialaccount/signup.html` - NEW FILE - Username selection page

## Verification Steps

### Manual Testing

1. **Traditional authentication still works**:
   - Go to `/signup/`, create account with username/password
   - Log out, log back in with same credentials
   - Verify Player object exists

2. **Google OAuth signup**:
   - Go to `/signup/`, click "Sign up with Google"
   - Complete Google OAuth flow
   - Should see username selection page
   - Choose username, submit
   - Verify logged in with chosen username
   - Verify email stored but not publicly visible

3. **Google OAuth login**:
   - Log out
   - Go to `/accounts/login/`, click "Sign in with Google"
   - Should log in immediately (no username selection)

4. **Bot API unaffected**:
   - Test `/three-way-login/` endpoint
   - Verify HTTP Basic Auth still works

### Automated Tests

Run existing tests to ensure backward compatibility:
```bash
just test
```

Add new tests in `project/app/test_social_auth.py`:
- Test Google button appears on login/signup pages
- Test traditional signup still works
- Test Player creation for OAuth users

### UI Tests

```bash
just ui-test-headless
```

Add Playwright tests to verify Google button is visible and clickable.

## Security & Backward Compatibility

- **Traditional auth**: Unchanged, ModelBackend remains
- **Bot API**: Completely unaffected
- **Existing users**: Can continue using username/password
- **Email privacy**: Email stored in User.email but not displayed
- **OAuth tokens**: Not stored (SOCIALACCOUNT_STORE_TOKENS = False)
- **CSRF protection**: All forms include CSRF tokens

## Rollback Plan

If issues occur:
1. Comment out allauth apps in INSTALLED_APPS
2. Remove allauth URLs from urls.py
3. Restart server
4. Traditional auth continues working

Complete rollback: Revert all changes, run `just uv-install`
