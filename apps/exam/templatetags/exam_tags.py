"""
exams/templatetags/exam_tags.py
────────────────────────────────
Custom template tags / filters for the exam module.
"""
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Access dict by key in Django templates.
    Usage: {{ my_dict|get_item:key_var }}
    Works for both int and str keys.
    """
    if dictionary is None:
        return None
    val = dictionary.get(key)
    if val is None:
        # Try with int/str coercion
        try:
            val = dictionary.get(int(key))
        except (TypeError, ValueError):
            pass
        if val is None:
            try:
                val = dictionary.get(str(key))
            except (TypeError, ValueError):
                pass
    return val


@register.filter
def duration_display(minutes):
    """Convert minutes to human-readable duration."""
    if not minutes:
        return "Unlimited"
    h = int(minutes) // 60
    m = int(minutes) % 60
    if h and m:
        return f"{h}h {m}m"
    elif h:
        return f"{h}h"
    return f"{m}m"


@register.simple_tag
def score_color_class(score, total):
    """Return Bootstrap color class based on percentage."""
    if not total:
        return "secondary"
    pct = (score / total) * 100
    if pct >= 75:
        return "success"
    elif pct >= 50:
        return "warning"
    else:
        return "danger"