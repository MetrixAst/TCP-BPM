import csv
from django.shortcuts import redirect, render
from django.http import HttpResponse
from django.views import View

from django.db.models import Q
from django.core.paginator import Paginator
from django.http import JsonResponse

from django.views.decorators.csrf import csrf_exempt

from django.contrib.auth.views import LoginView, LogoutView

from .role_permissions import need_permission, PermissionEnums, login_required

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

    _apply_profile_labels(request, profile_form, password_form)

    context = {
        'info': request.user.get_info(),
        'profile_form': profile_form,
        'password_form': password_form,
    }

    return render(request, 'site/account/profile.html', context)


def _apply_profile_labels(request, profile_form, password_form):
    from .i18n import translate, DEFAULT_LANG

    lang = getattr(request, 'current_lang', DEFAULT_LANG)

    for form in (profile_form, password_form):
        changed = False
        for name, field in form.fields.items():
            label = translate(lang, f'profile.fields.{name}', default=None)
            if label and label != f'profile.fields.{name}':
                field.label = label
                changed = True
        # CustomModelForm pins bound-field labels at init and Django caches
        # bound fields, so drop the cache to pick up the new field labels.
        if changed and hasattr(form, '_bound_fields_cache'):
            form._bound_fields_cache = {}


@login_required
@need_permission(PermissionEnums.HR)
def structure_csv(request, get):
    response = HttpResponse(content_type='text/csv')

    data = get_structure_data(request, get == 'all')
    writer = csv.writer(response)

    for current in data:
        writer.writerow(current)

    return response


@login_required
def global_search(request):
    """Глобальный поиск по шапке: разделы меню, сотрудники, документы, задачи,
    заявки, контрагенты, поставщики, арендаторы — с учётом прав доступа."""
    from django.urls import reverse
    from account.role_permissions import MenuItem, RoleEnums, RolePermissions

    query = (request.GET.get('q') or '').strip()
    if len(query) < 2:
        return JsonResponse({'results': [], 'groups': {}})

    ql = query.lower()
    results = []
    groups = {}

    def _add(group_key, group_label, title, subtitle, url):
        item = {'title': title, 'subtitle': subtitle, 'url': url, 'group': group_key}
        results.append(item)
        groups.setdefault(group_key, {'label': group_label, 'items': []})
        groups[group_key]['items'].append(item)

    # 1) Разделы из доступного пользователю меню (включая подпункты).
    def _walk(items):
        for item in items:
            url = getattr(item, 'url', None)
            title = getattr(item, 'title', None)
            if title and ql in title.lower() and url and url != '#' and not str(url).startswith('#'):
                _add('menu', 'Разделы', title, 'Раздел', url)
            if getattr(item, 'submenu', None):
                _walk(item.submenu)
    try:
        _walk(MenuItem.generate_menu(request.user))
    except Exception:
        pass

    role = getattr(request.user, 'role', None)
    viewer_is_admin = bool(getattr(request.user, 'is_superuser', False)) or role == RoleEnums.ADMINISTRATOR.value

    # 2) Сотрудники — только для внутренних ролей (не портал-арендаторов/гостей).
    if role not in RoleEnums.portal_roles():
        from account.models import Employee
        employees = (
            Employee.objects
            .select_related('user', 'position', 'department')
            .filter(
                Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(user__username__icontains=query)
                | Q(position__title__icontains=query)
            )
            .exclude(user__role=RoleEnums.ADMINISTRATOR.value)
            .exclude(user__is_superuser=True)
            .order_by('user__last_name', 'user__first_name')[:8]
        )
        for emp in employees:
            name = (emp.user.get_name or '').strip() or emp.user.username
            if emp.position_id:
                subtitle = emp.position.title
            elif emp.department_id:
                subtitle = emp.department.name
            else:
                subtitle = 'Сотрудник'
            if viewer_is_admin:
                subtitle = f'{subtitle} · логин: {emp.user.username}'
            _add('employees', 'Сотрудники', name, subtitle, reverse('hr:employee_detail', args=[emp.pk]))

    # 3) Документы — номер, название, текст.
    if RolePermissions.checkPermission(role, PermissionEnums.DOCUMENTS):
        from documents.models import Document
        try:
            docs = (
                Document.get_available_queryset(request)
                .filter(
                    Q(title__icontains=query)
                    | Q(number__icontains=query)
                    | Q(text__icontains=query)
                )
                .order_by('-id')[:8]
            )
            for doc in docs:
                _add(
                    'documents', 'Документы',
                    doc.title or doc.number or f'Документ #{doc.pk}',
                    doc.number or 'Документ',
                    reverse('documents:document', args=[doc.pk]),
                )
        except Exception:
            pass

    # 4) Задачи — заголовок, id как номер.
    if RolePermissions.checkPermission(role, PermissionEnums.TASKS):
        from tasks.models import Task
        try:
            task_filter = Q(title__icontains=query)
            if query.isdigit():
                task_filter |= Q(id=int(query))
            tasks_qs = (
                Task.get_available_queryset(request)
                .filter(task_filter)
                .order_by('-id')[:8]
            )
            for task in tasks_qs:
                _add(
                    'tasks', 'Задачи',
                    task.title or f'Задача #{task.pk}',
                    f'#{task.pk}',
                    reverse('tasks:task', args=[task.pk]),
                )
        except Exception:
            pass

   # 5) Сервисные заявки — заголовок, номер.
    if RolePermissions.checkPermission(role, PermissionEnums.SERVICE_REQUESTS):
        from tickets.models import ServiceRequest
        try:
            tickets_qs = (
                ServiceRequest.get_available_queryset(request)
                .filter(Q(title__icontains=query))
                .order_by('-id')[:8]
            )
            for ticket in tickets_qs:
                _add(
                    'tickets', 'Заявки',
                    ticket.title or ticket.number,
                    ticket.number or 'Заявка',
                    reverse('tickets:item', args=[ticket.pk]),
                )
        except Exception:
            pass

    # 6) Контрагенты — с учётом зон доступа.
    if RolePermissions.checkPermission(role, PermissionEnums.FINANCES) or RolePermissions.checkPermission(role, PermissionEnums.PURCHASES):
        from onec.models import Counterparty
        from account.services.access_scope import filter_counterparties_queryset
        try:
            cps = filter_counterparties_queryset(
                Counterparty.objects.filter(
                    Q(full_name__icontains=query)
                    | Q(short_name__icontains=query)
                    | Q(bin_number__icontains=query)
                ),
                request.user,
            ).order_by('short_name')[:8]
            for cp in cps:
                _add(
                    'counterparties', 'Контрагенты',
                    cp.short_name or cp.full_name,
                    cp.bin_number or 'Контрагент',
                    reverse('onec:counterparty_detail', args=[cp.pk]),
                )
        except Exception:
            pass

    # 7) Поставщики.
    if RolePermissions.checkPermission(role, PermissionEnums.SUPPLIERS):
        from purchases.models import Supplier
        try:
            suppliers = Supplier.objects.filter(name__icontains=query).order_by('name')[:8]
            for supplier in suppliers:
                _add(
                    'suppliers', 'Поставщики',
                    supplier.name,
                    'Поставщик',
                    reverse('purchases:supplier', args=[supplier.pk]),
                )
        except Exception:
            pass

    # 8) Арендаторы.
    if RolePermissions.checkPermission(role, PermissionEnums.TENANTS):
        from tenants.models import Tenant
        try:
            tenants_qs = Tenant.objects.filter(name__icontains=query).order_by('name')[:8]
            for tenant in tenants_qs:
                _add(
                    'tenants', 'Арендаторы',
                    tenant.name,
                    'Арендатор',
                    reverse('tenants:detail', args=[tenant.pk]),
                )
        except Exception:
            pass

    return JsonResponse({'results': results[:40], 'groups': groups})

@need_permission(PermissionEnums.USERS_LIST)
def users_ajax(request, selection):
    queryset = UserAccount.objects.all()

    query = request.GET.get('term', '')
    if query != '':
        queryset = queryset.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(username__icontains=query)
        )

    # Фильтр по отделу: только сотрудники выбранного отдела (с подотделами).
    department_id = request.GET.get('department')
    if department_id:
        from account.models import Department
        department = Department.objects.filter(pk=department_id).first()
        if department is not None:
            dept_ids = department.get_descendants(include_self=True).values_list('id', flat=True)
            queryset = queryset.filter(employee_info__department_id__in=list(dept_ids))
        else:
            queryset = queryset.none()

    page_number = request.GET.get('page', 1)
    paginator = Paginator(queryset, 25)
    objects = paginator.get_page(page_number)

    results = []
    for current in objects:
        try:
            addit = current.employee_info.position.title if current.employee_info.position else ''
        except Exception:
            addit = ''

        text = (current.get_name or '').strip() or current.username

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
                    item['submenu'].append({
                        'id': sub.id,
                        'title': sub.title,
                        'url': sub.url,
                    })

            res['menu'].append(item)

        res['first_page'] = MenuItem.first_page_as_string(request.user)

        res['user'] = {
            'name': request.user.get_name,
            'role': '',
            'avatar': request.user.get_avatar_url(),
        }

        employee = request.user.get_info()
        if employee is not None:
            res['user']['role'] = employee.position.title if employee.position else ''

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