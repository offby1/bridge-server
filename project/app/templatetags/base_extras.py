import contextlib
from typing import Any

from django import template
from django.conf import settings
from django.utils.html import format_html
from django.utils.timezone import now
import humanize

register = template.Library()


def gitlab_link(value: Any) -> str:
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


def humanized_timestamp(value: Any) -> str:
    if value is None:
        return "None"

    delta = value - now()
    suffix = "ago" if delta.total_seconds() < 0 else "from now"
    return format_html("""({} {})""", humanize.naturaldelta(delta), suffix)


register.filter("humanized_timestamp", humanized_timestamp)
