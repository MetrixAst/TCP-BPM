from django import forms

from account.models import UserAccount
from .models import PlanItem

INPUT = {'class': 'hr-form-input'}


class PlanItemForm(forms.ModelForm):
    class Meta:
        model = PlanItem
        fields = ['title', 'description', 'responsible', 'deadline', 'status', 'result']
        widgets = {
            'title': forms.TextInput(attrs={**INPUT, 'placeholder': 'Что нужно сделать'}),
            'description': forms.Textarea(attrs={**INPUT, 'rows': 2}),
            'responsible': forms.Select(attrs=INPUT),
            'deadline': forms.DateInput(attrs={**INPUT, 'type': 'date'}, format='%Y-%m-%d'),
            'status': forms.Select(attrs=INPUT),
            'result': forms.Textarea(attrs={**INPUT, 'rows': 2}),
        }

    def __init__(self, *args, plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsible'].required = True
        self.fields['deadline'].input_formats = ['%Y-%m-%d', '%d.%m.%Y']
        if plan is not None:
            dept_ids = plan.department.get_descendants(include_self=True).values_list('id', flat=True)
            in_department = UserAccount.objects.filter(
                employee_info__department_id__in=dept_ids, employee_info__status='active',
            )
            current = UserAccount.objects.filter(pk=self.instance.responsible_id)
            self.fields['responsible'].queryset = (in_department | current).distinct().order_by('last_name', 'first_name')
        self.fields['responsible'].label_from_instance = lambda u: u.get_name


class PlanItemProgressForm(forms.ModelForm):
    """Для ответственного: только статус и результат."""

    class Meta:
        model = PlanItem
        fields = ['status', 'result']
        widgets = {
            'status': forms.Select(attrs=INPUT),
            'result': forms.Textarea(attrs={**INPUT, 'rows': 2}),
        }
