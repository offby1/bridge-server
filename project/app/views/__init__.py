import logging

from django.contrib import messages as django_web_messages
from django.http import HttpResponseRedirect, HttpResponseNotFound, HttpResponseForbidden
from django.utils.html import escape, format_html
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.urls import reverse

from app.forms import SignupForm

logger = logging.getLogger(__name__)


def home_view(request):
    if hasattr(request.user, "player"):
        return HttpResponseRedirect(reverse("app:player", kwargs={"pk": request.user.player.pk}))
    return render(request, "home.html")


# TODO -- investigate https://docs.allauth.org/en/latest/mfa/introduction.html as a better way of signing up and
# authenticating
def signup_view(request):
    def start_over_with_message(message):
        django_web_messages.add_message(
            request,
            django_web_messages.INFO,
            message,
        )
        context["form"] = SignupForm()
        return TemplateResponse(request, "signup.html", context=context)

    context = {}

    if request.method == "GET":
        context["form"] = SignupForm()
        return TemplateResponse(request, "signup.html", context=context)

    if request.method == "POST":
        form = SignupForm(request.POST)
        if not form.is_valid():
            # TODO -- isn't there some fancy way to tart up the form with the errors?
            return start_over_with_message(f"Something's rotten in the state of {form.errors=}")

        # TODO: if it's a UNIQUE constraint failure, change the user's password
        try:
            form.create_user()
        except Exception as e:
            return start_over_with_message(str(e))

        return HttpResponseRedirect(reverse("login"))
    return None


def Forbid(e: Exception | str, content_type: str = "text/html") -> HttpResponseForbidden:
    logger.warning("%s", f"{e=}")
    if content_type == "text/html":
        tarted_up_html = format_html("<body>{}</body>", escape(e))
        return HttpResponseForbidden(tarted_up_html)

    # probably application/json but let's not be fussy
    return HttpResponseForbidden(str(e), content_type=content_type)


def NotFound(e: Exception | str) -> HttpResponseNotFound:
    return HttpResponseNotFound(escape(e))
