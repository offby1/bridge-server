from django import forms
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
    lookin_for_love = forms.ChoiceField(
        choices={True: "yes", False: "no", None: "don't care"},
        label="Lookin' for love?",
        required=False,
        widget=forms.RadioSelect,
    )


class SeatedForm(forms.Form):
    seated = forms.ChoiceField(
        choices={True: "yes", False: "no", None: "don't care"},
        label="Seated?",
        required=False,
        widget=forms.RadioSelect,
    )


# Does double-duty -- joins a partner, or breaks up with a partner.
class PartnerForm(forms.Form):
    me = forms.IntegerField(widget=forms.HiddenInput)
    them = forms.IntegerField(widget=forms.HiddenInput)
    action = forms.CharField(max_length=20, widget=forms.HiddenInput)
