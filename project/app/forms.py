from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Player


class SignupForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)
    password_again = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_again = cleaned_data.get("password_again")

        if password != password_again:
            raise ValidationError(
                f"{password=} != {password_again=}",
            )

    def create_user(self):
        u = User.objects.create_user(
            self.cleaned_data["username"],
            password=self.cleaned_data["password"],
        )
        Player.objects.create(user=u)


class LookingForLoveForm(forms.Form):
    lookin_for_love = forms.BooleanField(
        required=False,
        label="Lookin' for love?",
        widget=forms.NullBooleanSelect,
    )
