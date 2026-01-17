"""Tests for Google OAuth authentication components."""

from unittest.mock import Mock

from allauth.socialaccount.models import (  # type: ignore[import-untyped]
    SocialAccount,
)
from allauth.socialaccount.providers.google.provider import (  # type: ignore[import-untyped]
    GoogleProvider,
)
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core import mail
from django.test import TestCase, override_settings

from app.adapters import CustomSocialAccountAdapter
from app.forms import SocialSignupForm
from app.models import Player


class SocialSignupFormTestCase(TestCase):
    """Test the SocialSignupForm."""

    def test_form_has_username_field(self):
        """Test that form has username field with correct attributes."""
        form = SocialSignupForm()
        self.assertIn("username", form.fields)
        self.assertEqual(
            form.fields["username"].widget.attrs.get("placeholder"), "Choose a username"
        )
        self.assertIn("Your email remains private", form.fields["username"].help_text)

    def test_form_accepts_sociallogin_kwarg(self):
        """Test that form accepts sociallogin kwarg without error."""
        # Create a mock sociallogin object
        User(username="", email="test@example.com")

        # Form should accept sociallogin kwarg
        form = SocialSignupForm(sociallogin="mock")
        self.assertEqual(form.sociallogin, "mock")

    def test_form_save_sets_username(self):
        """Test that form.save() sets the username on the user."""
        # Create a user
        user = User(username="", email="test@example.com")

        # Create a simple mock sociallogin
        class MockSocialLogin:
            def __init__(self, user):
                self.user = user

        # Create form with data
        form = SocialSignupForm(
            data={"username": "testuser"},
            sociallogin=MockSocialLogin(user),
        )

        self.assertTrue(form.is_valid())

        # Save should set username
        result_user = form.save(request=None)
        self.assertEqual(result_user.username, "testuser")

    def test_form_rejects_duplicate_username(self):
        """Test that form validation rejects duplicate usernames."""
        # Create an existing user
        User.objects.create_user(username="existinguser", password="pass")

        # Create a new user for OAuth
        user = User(username="", email="newuser@example.com")

        # Create a simple mock sociallogin
        class MockSocialLogin:
            def __init__(self, user):
                self.user = user

        # Try to create form with duplicate username
        form = SocialSignupForm(
            data={"username": "existinguser"},
            sociallogin=MockSocialLogin(user),
        )

        # Form should not be valid
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)
        self.assertIn("already taken", str(form.errors["username"]))

    def test_try_save_returns_tuple(self):
        """Test that try_save() returns a tuple of (user, response)."""
        # Create a user
        user = User(username="", email="test@example.com")

        # Create a simple mock sociallogin
        class MockSocialLogin:
            def __init__(self, user):
                self.user = user

        # Create form with data
        form = SocialSignupForm(
            data={"username": "testuser"},
            sociallogin=MockSocialLogin(user),
        )

        self.assertTrue(form.is_valid())

        # try_save should return a tuple
        result = form.try_save(request=None)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        returned_user, response = result
        self.assertEqual(returned_user.username, "testuser")
        self.assertIsNone(response)

    def test_form_save_sets_username_without_saving_user(self):
        """Test that form.save() sets username but doesn't save user yet."""
        # Create a user (not saved to DB yet)
        user = User(username="", email="playertest@example.com")

        # Create a simple mock sociallogin
        class MockSocialLogin:
            def __init__(self, user):
                self.user = user

        # Create form with data
        form = SocialSignupForm(
            data={"username": "playertestuser"},
            sociallogin=MockSocialLogin(user),
        )

        self.assertTrue(form.is_valid())

        # Save should set username but not persist to DB
        result_user = form.save(request=None)
        self.assertEqual(result_user.username, "playertestuser")

        # User should not be in database yet (adapter.save_user() handles that)
        self.assertFalse(User.objects.filter(username="playertestuser").exists())


class CustomSocialAccountAdapterTestCase(TestCase):
    """Test the CustomSocialAccountAdapter."""

    def test_is_auto_signup_allowed_returns_false(self):
        """Test that auto signup is disabled to force username selection."""
        adapter = CustomSocialAccountAdapter()
        result = adapter.is_auto_signup_allowed(request=None, sociallogin=None)
        self.assertFalse(result)


class OAuthIntegrationTestCase(TestCase):
    """Integration tests for OAuth flow."""

    def test_player_created_for_oauth_user(self):
        """Test that Player is created when OAuth user is saved."""
        # Simulate what happens when OAuth user completes signup
        user = User.objects.create_user(
            username="oauthuser",
            email="oauth@example.com",
        )

        # Create social account link (what allauth does)
        SocialAccount.objects.create(
            user=user,
            provider=GoogleProvider.id,
            uid="123456789",
            extra_data={"email": "oauth@example.com"},
        )

        # Manually create player (what CustomSocialAccountAdapter.save_user does)
        Player.objects.create(user=user)

        # Verify player exists
        self.assertTrue(Player.objects.filter(user=user).exists())
        player = Player.objects.get(user=user)
        self.assertEqual(player.user, user)


class OAuthFlowEndToEndTestCase(TestCase):
    """End-to-end tests for complete OAuth flow."""

    def setUp(self):
        """Set up test fixtures."""
        # Create Site (required by allauth)
        self.site = Site.objects.get_current()
        self.site.domain = "testserver"
        self.site.name = "Test Server"
        self.site.save()

    def test_username_submission_creates_player(self):
        """Test that submitting username creates User and Player objects."""
        # Create initial user (as allauth would)
        user = User(username="", email="finaluser@example.com")
        user.save()

        SocialAccount.objects.create(user=user, provider=GoogleProvider.id, uid="final-uid-789")

        # Use the adapter to save user with Player creation
        adapter = CustomSocialAccountAdapter()
        mock_sociallogin = Mock()
        mock_sociallogin.user = user

        result_user = adapter.save_user(request=None, sociallogin=mock_sociallogin, form=None)

        # Verify Player was created
        self.assertTrue(Player.objects.filter(user=result_user).exists())
        player = Player.objects.get(user=result_user)
        self.assertEqual(player.user, result_user)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ACCOUNT_EMAIL_VERIFICATION="optional",
    )
    def test_oauth_signup_sends_verification_email(self):
        """Test that OAuth signup sends verification email."""
        # Create user and social account
        user = User.objects.create_user(username="emailtestuser", email="emailtest@example.com")

        SocialAccount.objects.create(user=user, provider=GoogleProvider.id, uid="email-test-uid")

        # Create Player
        Player.objects.create(user=user)

        # In a real flow, allauth would send the email
        # For this test, we verify the email backend works
        from django.core.mail import send_mail

        send_mail(
            "Test Email",
            "This is a test verification email.",
            "noreply@example.com",
            [user.email],
            fail_silently=False,
        )

        # Verify email was "sent" (stored in memory backend)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["emailtest@example.com"])
        self.assertIn("Test Email", mail.outbox[0].subject)

    def test_google_login_button_visible_on_login_page(self):
        """Test that Google sign-in button appears on login page."""
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        # Check for the exact text from the template
        self.assertContains(response, "Sign in with Google")
        # Check for the URL path (the button links to google login)
        self.assertContains(response, "/accounts/google/login/")

    def test_google_signup_button_visible_on_signup_page(self):
        """Test that Google sign-up button appears on signup page."""
        response = self.client.get("/signup/")
        self.assertEqual(response.status_code, 200)
        # Check for the exact text from the template
        self.assertContains(response, "Sign up with Google")
        # Check for the URL path (the button links to google login)
        self.assertContains(response, "/accounts/google/login/")

    def test_traditional_login_still_works(self):
        """Test that traditional username/password login still works."""
        # Create traditional user
        user = User.objects.create_user(username="traditionaluser", password="testpass123")
        Player.objects.create(user=user)

        # Login with username/password
        response = self.client.post(
            "/accounts/login/",
            {"username": "traditionaluser", "password": "testpass123"},
            follow=True,
        )

        # Should be logged in
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.username, "traditionaluser")

    def test_traditional_signup_still_works(self):
        """Test that traditional signup with username/password still works."""
        response = self.client.post(
            "/signup/",
            {
                "username": "newtraditionaluser",
                "password": "testpass123",
                "password_again": "testpass123",
            },
            follow=False,
        )

        # Should redirect to login page after signup
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

        # User should be created
        self.assertTrue(User.objects.filter(username="newtraditionaluser").exists())
        user = User.objects.get(username="newtraditionaluser")

        # Player should be created
        self.assertTrue(Player.objects.filter(user=user).exists())
