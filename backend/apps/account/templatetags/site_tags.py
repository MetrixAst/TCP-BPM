from django import template
from django.utils.safestring import mark_safe

from addits.models import Comment
from account.role_permissions import RolePermissions
from account.i18n import translate, build_lang_url, DEFAULT_LANG

register = template.Library()


# ── Иконки разделов бокового меню ─────────────────────────────────────────────
# Единый набор аккуратных outline-иконок (24×24, currentColor). Ключ — id пункта
# меню (MenuItem.id). Для неизвестных ключей используется нейтральная иконка.
NAV_ICON_PATHS = {
    'my_profile': '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    'tasks': '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
    'documents': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    'tenants': '<rect width="16" height="20" x="4" y="2" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/>',
    'purchases': '<circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/>',
    'finances': '<path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4Z"/>',
    'hr': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    'onec': '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/>',
    'ecopark': '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    'tickets': '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>',
    'reports': '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    'my_requisitions': '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
}
NAV_ICON_DEFAULT = '<circle cx="12" cy="12" r="9"/>'


@register.simple_tag
def nav_icon(menu_id, extra_class=''):
    """Возвращает inline-SVG иконки раздела по id пункта меню."""
    inner = NAV_ICON_PATHS.get(str(menu_id), NAV_ICON_DEFAULT)
    css = 'bpm-sidebar__icon'
    if extra_class:
        css += ' ' + extra_class
    return mark_safe(
        f'<svg class="{css}" width="18" height="18" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{inner}</svg>'
    )


@register.simple_tag(takes_context=True)
def t(context, key, default=''):
    request = context.get('request')
    lang = getattr(request, 'current_lang', DEFAULT_LANG) if request else DEFAULT_LANG
    return translate(lang, key, default=default or key)


@register.simple_tag(takes_context=True)
def lang_url(context, lang):
    request = context.get('request')
    if not request:
        return f'?lang={lang}'
    return build_lang_url(request, lang)


@register.simple_tag(takes_context=True)
def menu_t(context, menu_id, default=''):
    request = context.get('request')
    lang = getattr(request, 'current_lang', DEFAULT_LANG) if request else DEFAULT_LANG
    return translate(lang, f'menu.{menu_id}', default=default or menu_id)


@register.simple_tag(takes_context=True)
def role_label(context, role):
    request = context.get('request')
    lang = getattr(request, 'current_lang', DEFAULT_LANG) if request else DEFAULT_LANG
    if hasattr(role, 'value'):
        role = role.value
    key = f'sidebar.role_{role}'
    translated = translate(lang, key, default=None)
    if translated and translated != key:
        return translated
    return str(role)


@register.filter(name='has_permission')
def has_permission(user, permission):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    role = user.role
    if hasattr(role, 'value'):
        role = role.value
    return RolePermissions.checkPermission(role, permission)


@register.inclusion_tag('site/layouts/form.html', takes_context=True)
def init_form(context, form, additional_style = False):
    return {
        'form': form,
        'additional_style': additional_style,
        'request': context.get('request'),
    }


@register.inclusion_tag('site/layouts/form_errors.html')
def check_form(form):
    return {'form': form}


@register.inclusion_tag('site/layouts/paginator.html', takes_context=True)
def show_paginator(context, paginator, as_paginator_handler=False):
    request = context.get('request')
    base_qs = ''
    if request is not None:
        q = request.GET.copy()
        q.pop('page', None)
        base_qs = q.urlencode()
    return {
        'paginator': paginator,
        'as_paginator_handler': as_paginator_handler,
        'paginator_base_qs': base_qs,
    }

@register.inclusion_tag('site/layouts/comments.html')
def load_comments(target_type, target_id):

    comments = Comment.objects.filter(target_type=target_type, target_id=target_id)

    return {
        'comments': comments,
        'target_type': target_type,
        'target_id': target_id,
        'total': comments.count(),
    }



@register.inclusion_tag('site/documents/document_frame.html')
def document_frame(request, document):
    from documents import onlyoffice
    from account.role_permissions import RolePermissions, PermissionEnums

    has_file = bool(getattr(document, 'document', None))
    filename = document.document.name if has_file else ''
    oo_enabled = has_file and onlyoffice.is_enabled() and onlyoffice.is_supported(filename)

    can_edit = False
    if oo_enabled and onlyoffice.is_editable(filename):
        user = request.user
        if RolePermissions.checkPermission(user.role, PermissionEnums.EDIT_DOCUMENT):
            can_edit = (document.author_id == user.id) or \
                document.coordinators.filter(id=user.id).exists()

    return {
        'document': document,
        'full_url': request.build_absolute_uri(document.document.url) if has_file else '',
        'oo_enabled': oo_enabled,
        'oo_can_edit': can_edit,
    }

@register.filter(name='get_item')
def get_item(obj, key):
    """
    Универсальный доступ к атрибуту/ключу по строковой переменной.
 
    Работает с:
      - dict:          row|get_item:'name'  →  row['name']
      - object/model:  row|get_item:'name'  →  row.name
      - list:          row|get_item:0       →  row[0]
 
    Пример в шаблоне:
      {% for col in columns %}
        {{ row|get_item:col.key }}
      {% endfor %}
    """
    if obj is None:
        return ''
    if isinstance(obj, dict):
        return obj.get(key, '')
    if hasattr(obj, str(key)):
        return getattr(obj, str(key))
    try:
        return obj[key]
    except (KeyError, TypeError, IndexError):
        return ''
 
 
@register.filter(name='dict_get')
def dict_get(d, key):
    """Алиас get_item для словарей."""
    if isinstance(d, dict):
        return d.get(key, '')
    return ''
 

@register.filter(name='addclass')
def addclass(field, css_class):
    """
    Добавляет CSS-класс к Django form field.
    Использование: {{ form.name|addclass:'form-control' }}
    """
    if hasattr(field, 'as_widget'):
        return field.as_widget(attrs={'class': css_class})
    return field
 
 
@register.filter(name='placeholder')
def set_placeholder(field, placeholder_text):
    """
    Устанавливает placeholder для Django form field.
    Использование: {{ form.email|placeholder:'Введите email' }}
    """
    if hasattr(field, 'as_widget'):
        return field.as_widget(attrs={'placeholder': placeholder_text})
    return field
 
 
@register.filter(name='attr')
def set_attr(field, attr_str):
    """
    Устанавливает произвольный атрибут для Django form field.
    Использование: {{ form.name|attr:'data-validate:true' }}
    """
    if hasattr(field, 'as_widget'):
        key, _, value = attr_str.partition(':')
        return field.as_widget(attrs={key.strip(): value.strip()})
    return field
 
 
@register.simple_tag
def active_if(request_path, url):
    """
    Возвращает 'active' если текущий путь начинается с url.
    Использование: {% active_if request.path '/finances/' %}
    """
    if request_path.startswith(url):
        return 'active'
    return ''
 
 
@register.filter(name='multiply')
def multiply(value, arg):
    """{{ value|multiply:2 }}"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''
 
 
@register.filter(name='subtract')
def subtract(value, arg):
    """{{ value|subtract:1 }}"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return ''