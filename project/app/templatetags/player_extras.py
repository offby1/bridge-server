from django import template
from django.contrib.auth.models import User
from django.utils.html import format_html

import app.rendering
from app.models import Player

register = template.Library()

register.filter("player_link", app.rendering.player_link)
register.filter("player_display_name", app.rendering.player_display_name)


def sedate_link(value, arg):
    return styled_link(value, arg, style_attrs=[])


register.filter("sedate_link", sedate_link)


def styled_link(value: Player, arg: User, style_attrs=None):
    if style_attrs is None:
        style_attrs = ["font-size: 3vw"]
    comment = ""

    subject = value
    del value
    viewer = arg

    if hasattr(viewer, "player") and subject.pk == viewer.player.pk:
        style_attrs.append("color:green")
        comment = " (that's you!)"

    return format_html(
        "{}{}",
        app.rendering.player_link(subject, style=";".join(style_attrs)),
        comment,
    )


register.filter("styled_link", styled_link)
