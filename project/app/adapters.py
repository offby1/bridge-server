from allauth.socialaccount.adapter import (  # type: ignore [import-untyped]
    DefaultSocialAccountAdapter,
)

from app.models import Player


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter to handle social account signup flow.
    Forces username selection for OAuth users and creates Player objects.
    """

    def is_auto_signup_allowed(self, request, sociallogin):
        """Return False to force username selection page."""
        return False

    def save_user(self, request, sociallogin, form=None):
        """Save the user and create associated Player object."""
        user = super().save_user(request, sociallogin, form)
        # Create Player object for social account users
        if not hasattr(user, "player"):
            Player.objects.create(user=user)
        return user
