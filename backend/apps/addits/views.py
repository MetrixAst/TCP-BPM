from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from .models import Comment


class CommentView(View):

    def post(self, request, target_type, target_id):
        text = request.POST.get('text', None)
        if text is not None:
            res = Comment.create_comment(target_type, target_id, request.user, text)
            if res is not None:
                return JsonResponse({
                    'avatar': res.user.get_avatar_url(),
                    'name': res.user.get_name,
                    'date': res.formatted_date,
                    'text': text,
                })
            
        return JsonResponse({}, status=500)


def custom_page_not_found_view(request, exception):
    return render(request, "site/error.html", {'title': 'Страница не найдена', 'text': 'Этой страницы не существует, или она была удалена!'})

def custom_error_view(request, exception=None):
    return render(request, "site/error.html", {'title': 'Произошла ошибка', 'text': 'Не удалось выполнить запрос!'})

def custom_permission_denied_view(request, exception=None):
    return render(request, "site/error.html", {'title': 'Нет доступа', 'text': 'У Вас недостаточно прав для доступа к этой странице!'})