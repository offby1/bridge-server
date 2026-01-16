from allauth.socialaccount.forms import (
    SignupForm as SocialAccountSignupForm,  # type: ignore [import-untyped]
)
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


class SocialSignupForm(SocialAccountSignupForm):
    """
    Custom signup form for social account users (Google OAuth).
    Allows users to choose a custom username when signing up with Google.
    Only asks for username - email comes from OAuth provider.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Customize the username field
        self.fields["username"].widget.attrs.update(
            {"autofocus": True, "placeholder": "Choose a username", "class": "form-control"}
        )
        self.fields[
            "username"
        ].help_text = "This username will be visible to other players. Your email remains private."

    def save(self, request):
        """Save the user with the chosen username."""
        user = super().save(request)
        # Player creation is handled by CustomSocialAccountAdapter.save_user()
        return user
