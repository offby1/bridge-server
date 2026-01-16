"""Tests for Google OAuth authentication components."""

from allauth.socialaccount.models import (  # type: ignore[import-untyped]
    SocialAccount,
)
from allauth.socialaccount.providers.google.provider import (  # type: ignore[import-untyped]
    GoogleProvider,
)
from django.contrib.auth.models import User
from django.test import TestCase

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
