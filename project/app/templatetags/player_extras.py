from django import template
from django.utils.html import format_html

register = template.Library()


def sedate_link(value, arg):
    return styled_link(value, arg, style_attrs=[])


register.filter("sedate_link", sedate_link)


def styled_link(value, arg, style_attrs=None):
    if style_attrs is None:
        style_attrs = ["font-size: xx-large"]
    comment = ""

    subject = value
    del value
    viewer = arg

    if subject == viewer:
        style_attrs.append("color:green")
        comment = " (that's you!)"

    return format_html(
        "{}{}",
        subject.as_link(style=";".join(style_attrs)),
        comment,
    )


register.filter("styled_link", styled_link)
