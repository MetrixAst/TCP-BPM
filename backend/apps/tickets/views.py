import json

from django.shortcuts import redirect, render
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from account.role_permissions import need_permission, PermissionEnums
from project.paginator import CustomPaginator

from .models import ServiceRequest, user_is_manager
from .enums import TicketStatusEnum, TicketCategoryEnum
from .forms import TenantTicketForm, StaffTicketForm, TicketAssignForm


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _portal_context(request):
    return {
        'is_manager': user_is_manager(request.user),
        'is_portal_user': request.user.is_portal_user,
        'portal_tenant': getattr(request.user, 'tenant', None),
    }


def _card_dict(ticket):
    pr = ticket.priority_info
    st = ticket.status_info
    return {
        'id': ticket.id,
        'number': ticket.number,
        'title': ticket.title,
        'category': ticket.get_category_display(),
        'priority': ticket.priority,
        'priority_title': pr.get('title'),
        'priority_color': pr.get('color', 'neutral'),
        'status': ticket.status,
        'status_title': st.get('title'),
        'status_color': st.get('color', 'neutral'),
        'tenant': str(ticket.tenant) if ticket.tenant else None,
        'room': ticket.room,
        'assignee': ticket.assignee.get_name if ticket.assignee else None,
        'department': ticket.department.name if ticket.department else None,
        'created_at': ticket.created_at.strftime('%d.%m.%Y %H:%M') if ticket.created_at else None,
        'url': reverse('tickets:item', args=[ticket.id]),
    }


def _kanban_payload(request):
    qs = ServiceRequest.get_available_queryset(request)
    buckets = {}
    for ticket in qs:
        buckets.setdefault(ticket.status, []).append(ticket)
    columns = []
    for status in TicketStatusEnum.board_statuses():
        slug = status.value[0]
        info = TicketStatusEnum.get_info(slug)
        cards = [_card_dict(t) for t in buckets.get(slug, [])]
        columns.append({
            'status': slug,
            'title': info['title'],
            'color': info['color'],
            'count': len(cards),
            'tickets': cards,
        })
    return {'columns': columns}


@need_permission(PermissionEnums.SERVICE_REQUESTS)
def tickets(request):
    queryset = ServiceRequest.get_available_queryset(request)

    status = request.GET.get('status') or ''
    category = request.GET.get('category') or ''
    if status:
        queryset = queryset.filter(status=status)
    if category:
        queryset = queryset.filter(category=category)

    paginator = CustomPaginator(queryset, request.GET.get('page', 1))

    context = {
        'paginator': paginator,
        'statuses': TicketStatusEnum.list(),
        'categories': TicketCategoryEnum.list(),
        'active_status': status,
        'active_category': category,
        **_portal_context(request),
    }
    return render(request, 'site/tickets/tickets.html', context)


@need_permission(PermissionEnums.SERVICE_REQUESTS)
def kanban(request):
    if not user_is_manager(request.user):
        return redirect('tickets:home')
    return render(request, 'site/tickets/kanban.html', _portal_context(request))


@need_permission(PermissionEnums.SERVICE_REQUESTS)
@require_http_methods(['GET'])
def kanban_api(request):
    if not user_is_manager(request.user):
        return JsonResponse({'ok': False, 'message': 'Недоступно'}, status=403)
    return JsonResponse(_kanban_payload(request))


@need_permission(PermissionEnums.SERVICE_REQUESTS)
@require_http_methods(['PATCH', 'POST'])
def kanban_status(request, pk):
    if not user_is_manager(request.user):
        return JsonResponse({'ok': False, 'message': 'Недоступно'}, status=403)

    if request.content_type and 'application/json' in request.content_type:
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = request.POST

    ticket = ServiceRequest.get_by_id(request, pk)
    target = payload.get('status')
    comment = payload.get('comment', '')

    assignee = None
    assignee_id = payload.get('assignee_id')
    if assignee_id:
        from account.models import UserAccount
        assignee = UserAccount.objects.filter(pk=assignee_id).first()

    match = next((a for a in ticket.actions(request) if a['next'] == target), None)
    if match is None:
        return JsonResponse(
            {'ok': False, 'message': 'Недопустимый переход статуса'}, status=400,
        )
    ok, error = ticket.apply_action(request, match['action'], comment, assignee=assignee)
    if not ok:
        return JsonResponse({'ok': False, 'message': error}, status=400)
    return JsonResponse({'ok': True, 'kanban': _kanban_payload(request)})


@need_permission(PermissionEnums.SERVICE_REQUESTS)
def create(request):
    manager = user_is_manager(request.user)
    form = (StaffTicketForm if manager else TenantTicketForm)(
        request.POST or None, request.FILES or None,
    )

    if request.method == 'POST' and form.is_valid():
        ticket = form.save(commit=False)
        ticket.author = request.user
        if not manager:
            tenant = getattr(request.user, 'tenant', None)
            if tenant is not None:
                ticket.tenant = tenant
                if not ticket.room and tenant.room_id:
                    ticket.room = tenant.room.number
        ticket.status = TicketStatusEnum.NEW.value[0]
        ticket.save()
        from .models import ServiceRequestHistory
        ServiceRequestHistory.objects.create(
            request=ticket, user=request.user, status=ticket.status,
            comment='Заявка создана.',
        )
        from .services import notify_ticket_created
        notify_ticket_created(ticket)
        return redirect('tickets:item', pk=ticket.id)

    context = {'form': form, **_portal_context(request)}
    return render(request, 'site/tickets/create.html', context)


@need_permission(PermissionEnums.SERVICE_REQUESTS)
def item(request, pk):
    ticket = ServiceRequest.get_by_id(request, pk)
    from .models import TicketMessage
    context = {
        'ticket': ticket,
        'info': ticket.get_data(),
        'actions': ticket.actions(request),
        'assign_form': TicketAssignForm(instance=ticket) if user_is_manager(request.user) else None,
        'can_chat': TicketMessage.can_view(ticket, request.user),
        **_portal_context(request),
    }
    return render(request, 'site/tickets/ticket.html', context)


@need_permission(PermissionEnums.SERVICE_REQUESTS)
@require_http_methods(['POST'])
def action(request, pk):
    ticket = ServiceRequest.get_by_id(request, pk)
    act = request.POST.get('action')
    comment = request.POST.get('comment', '')

    assignee = None
    assignee_id = request.POST.get('assignee_id')
    if assignee_id:
        from account.models import UserAccount
        assignee = UserAccount.objects.filter(pk=assignee_id).first()

    allowed = {a['action']: a for a in ticket.actions(request)}
    if act not in allowed:
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': 'Действие недоступно'}, status=403)
        return HttpResponseForbidden('Действие недоступно')

    ok, error = ticket.apply_action(request, act, comment, assignee=assignee)
    if not ok:
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': error}, status=400)
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest(error)
    if _is_ajax(request):
        return JsonResponse({'ok': True, 'status': ticket.status})
    return redirect('tickets:item', pk=pk)


@need_permission(PermissionEnums.SERVICE_REQUESTS)
@require_http_methods(['POST'])
def assign(request, pk):
    ticket = ServiceRequest.get_by_id(request, pk)
    if not user_is_manager(request.user):
        return HttpResponseForbidden('Недоступно')
    form = TicketAssignForm(request.POST, instance=ServiceRequest())
    if form.is_valid():
        ticket.assign(
            request,
            department=form.cleaned_data.get('department'),
            assignee=form.cleaned_data.get('assignee'),
            priority=form.cleaned_data.get('priority'),
        )
    return redirect('tickets:item', pk=pk)

@need_permission(PermissionEnums.SERVICE_REQUESTS)
def messages_list(request, pk):
    ticket = ServiceRequest.get_by_id(request, pk)
    from .models import TicketMessage
    if not TicketMessage.can_view(ticket, request.user):
        return JsonResponse({'ok': False, 'message': 'Нет доступа к чату'}, status=403)

    messages = ticket.messages.select_related('author').all()
    return JsonResponse({
        'ok': True,
        'messages': [
            {
                'id': m.id,
                'text': m.text,
                'author': m.author.get_name if m.author else None,
                'author_id': m.author_id,
                'created_at': m.created_at.strftime('%d.%m.%Y %H:%M'),
            }
            for m in messages
        ],
    })


@need_permission(PermissionEnums.SERVICE_REQUESTS)
@require_http_methods(['POST'])
def message_send(request, pk):
    ticket = ServiceRequest.get_by_id(request, pk)
    from .models import TicketMessage
    if not TicketMessage.can_view(ticket, request.user):
        return JsonResponse({'ok': False, 'message': 'Нет доступа к чату'}, status=403)

    text = (request.POST.get('text') or '').strip()
    if not text:
        return JsonResponse({'ok': False, 'message': 'Пустое сообщение'}, status=400)

    message = TicketMessage.objects.create(
        request=ticket, author=request.user, text=text,
    )
    return JsonResponse({
        'ok': True,
        'message': {
            'id': message.id,
            'text': message.text,
            'author': message.author.get_name,
            'author_id': message.author_id,
            'created_at': message.created_at.strftime('%d.%m.%Y %H:%M'),
        },
    })
