from django import template
from django.utils.html import format_html

register = template.Library()


def gitlab_link(value):
    version_blob = value
    del value

    commit_hash, _ = version_blob.split(" ")

    return format_html("https://gitlab.com/offby1/bridge-server/-/commit/{}", commit_hash)


register.filter("gitlab_link", gitlab_link)
