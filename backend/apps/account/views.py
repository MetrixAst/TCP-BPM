import csv
from django.shortcuts import redirect, render
from django.http import HttpResponse
from django.views import View

from django.db.models import Q
from django.core.paginator import Paginator
from django.http import JsonResponse

from django.views.decorators.csrf import csrf_exempt

from django.contrib.auth.views import LoginView, LogoutView

from .role_permissions import need_permission, PermissionEnums

from .forms import CustomAuthenticationForm, EditProfileForm, CustomPasswordChangeForm
from .utils import get_structure_data
from .models import UserAccount, PushToken, NotificationIndicator


#AUTH
from account.forms import CustomAuthenticationForm
from django.contrib.auth import login as auth_login

#MENU
from account.role_permissions import MenuItem


class CustomLoginView(LoginView):
    form_class = CustomAuthenticationForm
    template_name = "site/account/login.html"


class CustomLogoutView(LogoutView):
    pass


class GuestView(View):
    def post(self, request):

        user = UserAccount.create_guest()
        
        auth_login(request, user)
        return redirect('dashboard:base')


@need_permission(PermissionEnums.PROFILE)
def profile_view(request):

    profile_form = EditProfileForm(instance=request.user, prefix="profile")
    password_form = CustomPasswordChangeForm(request.user, prefix="password")

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'profile':
            profile_form = EditProfileForm(request.POST, instance=request.user, prefix="profile")
            if profile_form.is_valid():
                profile_form.save()
                
        elif form_type == 'password':
            password_form = CustomPasswordChangeForm(request.user, data=request.POST or None, prefix="password")
            if password_form.is_valid():
                password_form.save()

    context = {
        'info': request.user.get_info(),
        'profile_form': profile_form,
        'password_form': password_form,
    }

    return render(request, 'site/account/profile.html', context)


def structure_csv(request, get):
    
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="data.csv"'},
    )

    data = get_structure_data(request, get == 'all')
    writer = csv.writer(response)

    for current in data:
        writer.writerow(current)

    return response


@need_permission(PermissionEnums.USERS_LIST)
def users_ajax(request, selection):
    queryset = UserAccount.objects.all()

    query = request.GET.get('term', '')
    if query != '':
        queryset = queryset.filter(
            Q(first_name__icontains=query) | Q(username__icontains=query)
        )

    page_number = request.GET.get('page', 1)
    paginator = Paginator(queryset, 25)
    objects = paginator.get_page(page_number)

    results = []
    for current in objects:
        try:
            addit = current.employee_info.job_title
        except UserAccount.employee_info.RelatedObjectDoesNotExist:
            addit = ''

        text = ''
        if getattr(current, 'get_name', None):
            text = current.get_name

        if not text or not str(text).strip():
            text = current.username

        results.append({
            'id': current.id,
            'text': text,
            'addit': addit,
        })

    return JsonResponse({
        'results': results,
        'pagination': {
            'more': objects.has_next(),
        },
    })



#MOBILE VIEWS


@csrf_exempt
def auth(request):
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, request.POST)
        if form.is_valid():
            auth_login(request, form.get_user())
            return JsonResponse({'success': True, 'cookies': request.COOKIES})
        else:
            return JsonResponse({'success': False, 'error': 'Не удалось авторизоваться'})


    return JsonResponse({'success': False, 'error': 'Ошибка'})


@csrf_exempt
def push_token(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            token = request.POST.get('token', None)
            if token is not None:
                PushToken.objects.get_or_create(user=request.user, fcm=token)
                
                return JsonResponse({'success': True})
        elif request.method == 'DELETE':
            request.user.push_tokens.all().delete()
                
            return JsonResponse({'success': True})


    return JsonResponse({'success': False, 'error': 'Ошибка'})

def get_side_menu(request):
    if request.user.is_authenticated:
        indicators = NotificationIndicator.get_data(request.user)
        res = {
            'success': True, 
            'menu': [],
        }

        #MENU
        menu_items = MenuItem.generate_menu(request.user)
        for current in menu_items:
            item = {
                'id': current.id,
                'title': current.title,
                'url': current.url,
                'icon': current.icon,
                'indicator': indicators['counts'].get(current.indicator_alias, 0),
            }
            if current.submenu is not None:
                item['submenu'] = []
                for sub in current.submenu:
                    item['submenu'].append(
                        {
                            'id': sub.id,
                            'title': sub.title,
                            'url': sub.url,
                        }
                    )
            
            res['menu'].append(item)
        

        res['first_page'] = MenuItem.first_page_as_string(request.user)
        

        #NAME
        res['user'] = {
            'name': request.user.get_name,
            'role': '',
            'avatar': request.user.get_avatar_url(),
        }

        employee = request.user.get_info()
        if employee is not None:
            res['user']['role'] = employee.job_title
        
        print(res)

        return JsonResponse(res)
    else:
        return JsonResponse({'success': False, 'error': 'Требуется авторизация'})
    

def notifications_view(request):
    notifications = request.user.notifications.all()[:50]

    context = {
        'notifications_list': notifications,
    }

    return render(request, 'site/account/notifications.html', context)

def indicator_readed(request, target_id, target_type):
    if request.user.is_authenticated:
        NotificationIndicator.readed(request.user, target_id, target_type)
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False})