from django.http import JsonResponse
from django.shortcuts import redirect, render
from project.paginator import CustomPaginator
from django.http import Http404
from django.db.models import Q

from account.role_permissions import need_permission, PermissionEnums, RolePermissions
from project.utils import get_or_error
# from .enums import TaskStatusEnum
from .models import Tenant
from .serializers import TenantSerializer
import json

# from .forms import TaskForm

@need_permission(PermissionEnums.TENANTS)
def home(request):

    all_queryset = Tenant.objects.all()
    queryset = all_queryset
    search = request.GET.get('search', '')
    page = int(request.GET.get('page', 1))

    if search != '':
        queryset = queryset.filter(Q(name__icontains=search) | Q(number__icontains=search))

    paginator = CustomPaginator(queryset, page)


    
    serializer = TenantSerializer(all_queryset, many=True)
    output_dict = json.dumps(serializer.data)

    context = {
        'paginator': paginator,
        'tenants': output_dict,
    }


    return render(request, 'site/tenants/tenants.html', context)



@need_permission(PermissionEnums.TENANTS)
def all_json(request):

    queryset = Tenant.objects.all().exclude(room=None)
    res = []
    for current in queryset:
        res.append(current.to_json())

    return JsonResponse(res, safe=False)



