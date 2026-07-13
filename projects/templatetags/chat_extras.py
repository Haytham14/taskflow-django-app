import re

from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(needs_autoescape=True)
def mentionize(value, autoescape=True):
    escaped = conditional_escape(value) if autoescape else value
    rendered = re.sub(
        r"(?<!\w)@([\wÀ-ÿ.-]+)",
        r'<span class="chat-mention">@\1</span>',
        str(escaped),
    )
    return mark_safe(rendered)
