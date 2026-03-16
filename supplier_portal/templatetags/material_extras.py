from django import template
from ..models import Material

register = template.Library()

@register.filter
def material_name_by_id(material_id):
    try:
        return Material.objects.get(id=material_id).name
    except Exception:
        return "Không rõ vật tư"