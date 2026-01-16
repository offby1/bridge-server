from allauth.socialaccount.adapter import (
    DefaultSocialAccountAdapter,  # type: ignore [import-untyped]
)


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
