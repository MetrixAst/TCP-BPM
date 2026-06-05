from django import forms

from account.models import AccessScope, Department, UserAccount
from .models import Folder


ROLE_CHOICES = UserAccount.ROLES


class FolderAccessForm(forms.Form):
    scope_is_global = forms.BooleanField(
        label='Доступна всем',
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

    def __init__(self, folder, *args, **kwargs):
        self.folder = folder
        super().__init__(*args, **kwargs)
        scope = folder.access_scope
        if scope:
            self.fields['scope_is_global'].initial = scope.is_global
            self.fields['scope_roles'].initial = scope.roles or []
            self.fields['scope_departments'].initial = scope.departments.all()
            self.fields['scope_users'].initial = scope.users.all()

    def save(self):
        scope = self.folder.access_scope
        if scope is None:
            scope = AccessScope(name=self.folder.name)
        scope.name = f'{self.folder.name}'
        scope.is_global = self.cleaned_data.get('scope_is_global', False)
        scope.roles = self.cleaned_data.get('scope_roles') or []
        scope.save()
        scope.departments.set(self.cleaned_data.get('scope_departments') or [])
        scope.users.set(self.cleaned_data.get('scope_users') or [])
        self.folder.access_scope = scope
        self.folder.save(update_fields=['access_scope'])
        return scope
