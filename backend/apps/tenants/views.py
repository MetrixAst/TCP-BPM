import json
import os
from decimal import Decimal

from django.contrib import messages
from django.db.models import F, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from account.role_permissions import need_permission, PermissionEnums
from project.paginator import CustomPaginator
from .forms import TenantForm
from .models import Tenant, TenantCategory, TenantDocument, Room
from .serializers import TenantSerializer
from addits.models import Comment
from .qr_labels import generate_single_label_pdf, generate_batch_labels_pdf
from .services.portal_mail import send_tenant_portal_credentials


def _tenant_order_by(sort: str, order: str):
    """Сортировка списка арендаторов; пустые значения всегда в конце."""
    descending = order == 'desc'
    if sort == 'name':
        return (F('name').desc(nulls_last=True) if descending else F('name').asc(nulls_last=True),)
    if sort == 'end_date':
        primary = F('end_date').desc(nulls_last=True) if descending else F('end_date').asc(nulls_last=True)
        return (primary, 'name')
    primary = F('room__number').desc(nulls_last=True) if descending else F('room__number').asc(nulls_last=True)
    return (primary, 'name')


@need_permission(PermissionEnums.TENANTS)
def home(request):
    sort = request.GET.get('sort', 'room')
    if sort not in ('room', 'name', 'end_date'):
        sort = 'room'
    order = request.GET.get('order', 'asc')
    if order not in ('asc', 'desc'):
        order = 'asc'

    all_queryset = Tenant.objects.select_related('room', 'category').prefetch_related('portal_users').all()
    queryset = all_queryset
    search = request.GET.get('search', '')
    try:
        page = int(request.GET.get('page') or 1)
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        page = 1

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(room__number__icontains=search)
        )

    queryset = queryset.order_by(*_tenant_order_by(sort, order))

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
        'sort': sort,
        'order': order,
        'stats': {
            'total': all_queryset.count(),
            'on_map': on_map,
            'expiring': expiring,
            'warning': warning,
        },
    }

    return render(request, 'site/tenants/tenants.html', context)


@need_permission(PermissionEnums.TENANTS)
def tenant_detail(request, pk):
    current = (
        Tenant.objects.select_related('room', 'category')
        .filter(pk=pk)
        .first()
    )
    if current is None:
        raise Http404

    has_portal = current.portal_users.exists() if hasattr(current, 'portal_users') else False

    comments = Comment.objects.filter(
        target_type='tenant', target_id=current.pk
    ).select_related('user').order_by('id')

    documents = current.documents.select_related('uploaded_by').all()

    monthly_base_rent = (
        Decimal(str(current.area or 0)) * Decimal(str(current.price or 0))
    )
    lease_fields = (
        ('Начало аренды', current.start_date),
        ('Завершение аренды', current.end_date),
        ('Срок скидки', current.discount_date),
        ('Повышение ставки', current.increase_type),
        ('Ответственное лицо', current.contact),
        ('Телефон', current.phone),
        ('Email', current.email),
    )
    missing_lease_fields = [label for label, value in lease_fields if not value]
    lease_completeness = round(
        (len(lease_fields) - len(missing_lease_fields)) / len(lease_fields) * 100
    )

    return render(request, 'site/tenants/tenant_detail.html', {
        'tenant': current,
        'has_portal': has_portal,
        'comments': comments,
        'documents': documents,
        'monthly_base_rent': monthly_base_rent,
        'annual_base_rent': monthly_base_rent * 12,
        'missing_lease_fields': missing_lease_fields,
        'lease_completeness': lease_completeness,
        'can_edit': True,
    })


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

    send_email = request.POST.get('send_email', '1') not in ('0', 'false', 'False')
    mail_result = {'sent': False, 'error': None}
    if send_email:
        mail_result = send_tenant_portal_credentials(
            tenant=tenant,
            username=user.username,
            password=password,
            created=created,
            request=request,
        )

    return JsonResponse({
        'success': True,
        'created': created,
        'username': user.username,
        'password': password,
        'email_sent': mail_result['sent'],
        'email_error': mail_result['error'],
        'email_to': email if send_email else None,
    })


@need_permission(PermissionEnums.TENANTS)
@require_POST
def tenant_document_upload(request, pk):
    tenant = get_object_or_404(Tenant, pk=pk)
    uploaded = request.FILES.get('file')
    if not uploaded:
        messages.error(request, 'Выберите файл для загрузки.')
        return redirect('tenants:detail', pk=pk)

    title = (request.POST.get('title') or '').strip()
    if not title:
        title = os.path.basename(uploaded.name)

    TenantDocument.objects.create(
        tenant=tenant,
        title=title[:255],
        file=uploaded,
        uploaded_by=request.user if request.user.is_authenticated else None,
    )
    messages.success(request, f'Документ «{title}» добавлен.')
    return redirect(reverse('tenants:detail', args=[pk]) + '#docs')


@need_permission(PermissionEnums.TENANTS)
@require_POST
def tenant_document_delete(request, pk, doc_pk):
    tenant = get_object_or_404(Tenant, pk=pk)
    doc = get_object_or_404(TenantDocument, pk=doc_pk, tenant=tenant)
    name = doc.display_name
    if doc.file:
        doc.file.delete(save=False)
    doc.delete()
    messages.success(request, f'Документ «{name}» удалён.')
    return redirect(reverse('tenants:detail', args=[pk]) + '#docs')


@need_permission(PermissionEnums.TENANTS)
def room_qr_label(request, pk):
    """GET /tenants/rooms/<pk>/qr-label/ — PDF-наклейка для одного помещения."""
    room = get_object_or_404(Room, pk=pk)
    pdf_buffer = generate_single_label_pdf(room)

    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="qr_room_{room.number}.pdf"'
    return response


@need_permission(PermissionEnums.TENANTS)
def rooms_qr_labels_batch(request):
    """
    GET /tenants/rooms/qr-labels/ — PDF со всеми наклейками (лист А4, сетка).
    Опционально ?floor=<N> для фильтра по этажу.
    """
    rooms = Room.objects.all().order_by('number')

    floor = request.GET.get('floor')
    if floor:
        rooms = rooms.filter(floor=floor)

    if not rooms.exists():
        return HttpResponse('Помещения не найдены', status=404)

    pdf_buffer = generate_batch_labels_pdf(rooms)

    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="qr_labels_batch.pdf"'
    return response