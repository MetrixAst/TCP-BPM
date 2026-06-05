from django import forms

from addits.forms import CustomModelForm, TreeField, UserSelect2Field, Select2FieldDefault
from account.models import Department
from tenants.models import Tenant

from .models import ServiceRequest


class TenantTicketForm(CustomModelForm):
    """Создание заявки арендатором через портал."""

    class Meta:
        model = ServiceRequest
        fields = ('category', 'title', 'description', 'room', 'priority', 'photo')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Опишите проблему'}),
        }


class StaffTicketForm(CustomModelForm):
    """Создание заявки сотрудником (например, по звонку арендатора)."""

    tenant = Select2FieldDefault(queryset=Tenant.objects.all(), required=False, placeholder='Арендатор')
    department = TreeField(queryset=Department.objects.all(), required=False)
    assignee = UserSelect2Field(required=False, all=True, placeholder='Ответственный')

    class Meta:
        model = ServiceRequest
        fields = ('tenant', 'category', 'title', 'description', 'room',
                  'priority', 'department', 'assignee', 'photo')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Опишите проблему'}),
        }


class TicketAssignForm(CustomModelForm):
    """Маршрутизация заявки сотрудником: отдел / ответственный / приоритет."""

    department = TreeField(queryset=Department.objects.all(), required=False)
    assignee = UserSelect2Field(required=False, all=True, placeholder='Ответственный')

    class Meta:
        model = ServiceRequest
        fields = ('department', 'assignee', 'priority')
