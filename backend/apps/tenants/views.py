from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.db.models import Q
from django.views.decorators.http import require_POST
import json

from account.role_permissions import need_permission, PermissionEnums
from project.paginator import CustomPaginator
from .forms import TenantForm
from .models import Tenant, TenantCategory, Room
from .serializers import TenantSerializer


@need_permission(PermissionEnums.TENANTS)
def home(request):
    all_queryset = Tenant.objects.select_related('room', 'category').all()
    queryset = all_queryset
    search = request.GET.get('search', '')
    page = int(request.GET.get('page', 1))

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(room__number__icontains=search)
        )

    paginator = CustomPaginator(queryset, page)
    serializer = TenantSerializer(all_queryset, many=True)

    on_map = all_queryset.exclude(room__isnull=True).count()
    expiring = sum(1 for t in all_queryset if t.status == 'red')
    warning = sum(1 for t in all_queryset if t.status == 'yellow')

    context = {
        'paginator': paginator,
        'tenants': json.dumps(serializer.data),
        'tenant_form': TenantForm(),
        'categories': TenantCategory.objects.all(),
        'rooms': Room.objects.all(),
        'search': search,
        'stats': {
            'total': all_queryset.count(),
            'on_map': on_map,
            'expiring': expiring,
            'warning': warning,
        },
    }

    return render(request, 'site/tenants/tenants.html', context)


@need_permission(PermissionEnums.TENANTS)
@require_POST
def create_tenant(request):
    form = TenantForm(request.POST)

    if form.is_valid():
        tenant = form.save()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f'Арендатор «{tenant.name}» добавлен.',
                'tenant_id': tenant.id,
            })
        messages.success(request, f'Арендатор «{tenant.name}» добавлен.')
        return redirect('tenants:list')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)

    messages.error(request, 'Не удалось добавить арендатора. Проверьте данные.')
    return redirect('tenants:list')


@need_permission(PermissionEnums.TENANTS)
def all_json(request):
    queryset = Tenant.objects.all().exclude(room=None)
    res = [current.to_json() for current in queryset]
    return JsonResponse(res, safe=False)


@need_permission(PermissionEnums.TENANTS)
@require_POST
def tenant_portal_access(request, pk):
    """Создаёт/сбрасывает доступ арендатора в портал и возвращает логин/пароль.

    Логин арендатора — это его email. Если email не задан или занят другим
    пользователем платформы, возвращается понятная ошибка.
    """
    from django.utils.crypto import get_random_string
    from account.models import UserAccount
    from account.role_permissions import RoleEnums

    tenant = Tenant.objects.filter(pk=pk).first()
    if tenant is None:
        return JsonResponse({'success': False, 'message': 'Арендатор не найден'}, status=404)

    email = (tenant.email or '').strip().lower()
    if not email:
        return JsonResponse({
            'success': False,
            'message': 'У арендатора не указан email. Заполните email, чтобы выдать доступ — он будет логином.',
        }, status=400)

    user = tenant.portal_users.filter(role=RoleEnums.TENANT.value).order_by('id').first()
    created = user is None

    # email занят другим пользователем (не текущим арендатором) — блокируем,
    # иначе логин не совпал бы с email и вводил бы в заблуждение.
    clash = UserAccount.objects.filter(username=email)
    if user is not None:
        clash = clash.exclude(pk=user.pk)
    if clash.exists():
        return JsonResponse({
            'success': False,
            'message': f'Email «{email}» уже используется другим аккаунтом. Укажите другой email арендатора.',
        }, status=400)

    password = get_random_string(10)
    if created:
        user = UserAccount.create_tenant_user(tenant, username=email)
    else:
        # синхронизируем логин с актуальным email арендатора
        user.username = email
        user.email = email
    user.set_password(password)
    user.is_active = True
    user.save()

    return JsonResponse({
        'success': True,
        'created': created,
        'username': user.username,
        'password': password,
    })
