from django import forms

from account.models import AccessScope, Department, UserAccount
from .models import Counterparty, CounterpartyType


ROLE_CHOICES = UserAccount.ROLES


class CounterpartyTypeForm(forms.ModelForm):
    scope_is_global = forms.BooleanField(
        label='Доступен всем',
        required=False,
        initial=False,
    )
    scope_roles = forms.MultipleChoiceField(
        label='Роли',
        choices=ROLE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    scope_departments = forms.ModelMultipleChoiceField(
        label='Отделы',
        queryset=Department.objects.select_related('company').order_by('name'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': 8}),
    )
    scope_users = forms.ModelMultipleChoiceField(
        label='Пользователи',
        queryset=UserAccount.objects.filter(is_active=True).order_by('username'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': 8}),
    )

    class Meta:
        model = CounterpartyType
        fields = ('name', 'code', 'is_active', 'sort_order')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'supplier_kz'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'style': 'max-width:120px'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        scope = None
        if self.instance and self.instance.pk and self.instance.access_scope_id:
            scope = self.instance.access_scope
        if scope:
            self.fields['scope_is_global'].initial = scope.is_global
            self.fields['scope_roles'].initial = scope.roles or []
            self.fields['scope_departments'].initial = scope.departments.all()
            self.fields['scope_users'].initial = scope.users.all()

    def _save_access_scope(self, counterparty_type):
        scope = counterparty_type.access_scope
        if scope is None:
            scope = AccessScope(name=counterparty_type.name)
        scope.name = counterparty_type.name
        scope.is_global = self.cleaned_data.get('scope_is_global', False)
        scope.roles = self.cleaned_data.get('scope_roles') or []
        scope.save()
        scope.departments.set(self.cleaned_data.get('scope_departments') or [])
        scope.users.set(self.cleaned_data.get('scope_users') or [])
        counterparty_type.access_scope = scope
        counterparty_type.save(update_fields=['access_scope'])
        return scope

    def save(self, commit=True):
        counterparty_type = super().save(commit=commit)
        self._save_access_scope(counterparty_type)
        return counterparty_type


class CounterpartyForm(forms.ModelForm):
    class Meta:
        model = Counterparty
        fields = (
            'full_name',
            'short_name',
            'description',
            'bin_number',
            'iin',
            'address',
            'phone',
            'email',
            'website',
            'activity_type',
            'founded_date',
            'counterparty_type',
            'is_supplier',
            'is_customer',
        )
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Полное наименование'}),
            'short_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Краткое название'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Короткое описание'}),
            'bin_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12 цифр'}),
            'iin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ИИН (для ИП)'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'website': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'example.kz'}),
            'activity_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Вид деятельности'}),
            'founded_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Дата основания'}),
            'counterparty_type': forms.Select(attrs={'class': 'form-control'}),
            'is_supplier': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_customer': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['counterparty_type'].queryset = CounterpartyType.objects.filter(is_active=True)
        self.fields['counterparty_type'].required = False
        self.fields['counterparty_type'].empty_label = '— без типа (видят все) —'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.id_1c:
            import uuid
            instance.id_1c = f'bpm-{uuid.uuid4().hex[:12]}'
        if commit:
            instance.save()
            self.save_m2m()
        return instance
