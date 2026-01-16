from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Player


class SignupForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={"autofocus": True}))
    password = forms.CharField(widget=forms.PasswordInput)
    password_again = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_again = cleaned_data.get("password_again")

        if password != password_again:
            msg = f"{password=} != {password_again=}"
            raise ValidationError(
                msg,
            )

    def create_user(self) -> None:
        u = User.objects.create_user(
            self.cleaned_data["username"],
            password=self.cleaned_data["password"],
        )
        Player.objects.create(user=u)


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control", "autofocus": True})
    )
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))


class SocialSignupForm(forms.Form):
    """
    Custom signup form for social account users (Google OAuth).
    Allows users to choose a custom username when signing up with Google.
    Only asks for username - email comes from OAuth provider.
    """

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={"autofocus": True, "placeholder": "Choose a username", "class": "form-control"}
        ),
        help_text="This username will be visible to other players. Your email remains private.",
    )

    def __init__(self, *args, **kwargs):
        # Accept sociallogin kwarg that allauth passes, but we don't need it
        self.sociallogin = kwargs.pop("sociallogin", None)
        # Accept other allauth kwargs
        kwargs.pop("initial", None)
        kwargs.pop("email_addresses", None)
        super().__init__(*args, **kwargs)

    def clean_username(self):
        """Validate that username is unique."""
        username = self.cleaned_data.get("username")
        if User.objects.filter(username=username).exists():
            raise ValidationError("This username is already taken. Please choose another.")
        return username

    def try_save(self, request):
        """Try to save the form. Called by allauth during signup flow."""
        user = self.save(request)
        return user, None  # Return tuple of (user, response)

    def save(self, request):
        """Save the user with the chosen username. Called by allauth."""
        # Get the user from the sociallogin object
        user = self.sociallogin.user
        user.username = self.cleaned_data["username"]
        user.save()
        # Player creation is handled by CustomSocialAccountAdapter.save_user()
        return user
