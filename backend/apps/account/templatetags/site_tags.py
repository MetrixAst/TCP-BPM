from django import template
from addits.models import Comment

register = template.Library()


@register.inclusion_tag('site/layouts/form.html')
def init_form(form, additional_style = False):
    return {'form': form, 'additional_style': additional_style}


@register.inclusion_tag('site/layouts/form_errors.html')
def check_form(form):
    return {'form': form}


@register.inclusion_tag('site/layouts/paginator.html')
def show_paginator(paginator, as_paginator_handler = False):
    return {
        'paginator': paginator,
        'as_paginator_handler': as_paginator_handler,
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
    return {
        'document': document,
        'full_url': request.build_absolute_uri(document.document.url)
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