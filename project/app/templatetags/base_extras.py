import contextlib

from django import template
from django.conf import settings
from django.utils.html import format_html

register = template.Library()


def gitlab_link(value):
    version_blob = value
    del value

    commit_hash = None
    base_url = settings.GITLAB_HOMEPAGE
    with contextlib.suppress(ValueError):
        commit_hash, _ = version_blob.split(" ")
    if commit_hash:
        return format_html(base_url + "-/commit/{}", commit_hash)
    return base_url


register.filter("gitlab_link", gitlab_link)
