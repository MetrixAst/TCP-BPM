from django import forms

from addits.forms import CustomModelForm, TreeField, UserSelect2Field, Select2FieldDefault
from account.models import Department
from tenants.models import Tenant

from .models import ServiceRequest, TicketTypeConfig


class TenantTicketForm(CustomModelForm):
    """Создание заявки арендатором через портал."""

    class Meta:
        model = ServiceRequest
        # photo убран — вложения сохраняются через TicketAttachment
        fields = ('category', 'title', 'description', 'room', 'priority')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Опишите проблему'}),
        }


class StaffTicketForm(CustomModelForm):
    """Создание заявки сотрудником (например, по звонку арендатора)."""

    tenant = Select2FieldDefault(queryset=Tenant.objects.all(), required=False, placeholder='Арендатор')
    department = TreeField(queryset=Department.objects.all(), required=False)
    assignee = UserSelect2Field(required=False, all=True,)

    class Meta:
        model = ServiceRequest
        # photo убран — вложения сохраняются через TicketAttachment
        fields = ('tenant', 'category', 'title', 'description', 'room',
                  'priority', 'department', 'assignee')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Опишите проблему'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].widget.attrs['data-dept-source'] = '#id_department'


class TicketAssignForm(CustomModelForm):
    """Маршрутизация заявки сотрудником: отдел / ответственный / приоритет."""

    department = TreeField(queryset=Department.objects.all(), required=False)
    assignee = UserSelect2Field(required=False, all=True)

    class Meta:
        model = ServiceRequest
        fields = ('department', 'assignee', 'priority')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].widget.attrs['data-dept-source'] = '#id_department'

class TicketTypeConfigForm(forms.ModelForm):
    department = Select2FieldDefault(
        queryset=Department.objects.all(),
        placeholder='Все отделы',
        required=False,
    )
    auto_assign_to = UserSelect2Field(
        placeholder='Не назначать автоматически',
        required=False,
        all=True,
    )

    class Meta:
        model = TicketTypeConfig
        fields = ['ticket_type', 'department', 'requires_approval', 'sla_hours', 'auto_assign_to']
        widgets = {
            'sla_hours': forms.NumberInput(attrs={'min': 1, 'placeholder': 'Часов'}),
        }

