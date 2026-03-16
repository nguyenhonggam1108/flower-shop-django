# supplier_portal/templatetags/zip_extras.py
from django import template
register = template.Library()
@register.filter
def zip_lists(a, b):
    return zip(a, b)