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