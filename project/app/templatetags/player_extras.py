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
    if value == arg:
        style_attrs.append("color:green")
        comment = " (that's you!)"
    elif value == arg.partner:
        style_attrs.append("color:red")
        comment = "✨MUH PARTNER✨"
    return format_html(
        "{}{}",
        value.as_link(style=";".join(style_attrs)),
        comment,
    )


register.filter("styled_link", styled_link)
