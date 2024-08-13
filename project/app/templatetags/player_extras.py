from django import template
from django.utils.html import format_html

register = template.Library()


def styled_link(value, arg):
    style_attrs = ["font-size: xx-large"]
    comment = ""
    if value == arg:
        style_attrs.append("color:green")
        comment = " (that's you!)"
    return format_html(
        "{}{}",
        value.as_link(style=";".join(style_attrs)),
        comment,
    )


register.filter("styled_link", styled_link)
