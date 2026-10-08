from django import forms

from account.models import AccessScope, Department, UserAccount


ROLE_CHOICES = UserAccount.ROLES


class _AccessScopeFormBase(forms.Form):
    def _load_scope_initial(self, scope):
        if scope:
            self.fields['scope_is_global'].initial = scope.is_global
            self.fields['scope_roles'].initial = scope.roles or []
            self.fields['scope_departments'].initial = scope.departments.all()
            self.fields['scope_users'].initial = scope.users.all()
        else:
            self.fields['scope_is_global'].initial = True

    def _save_scope(self, *, name: str, existing: AccessScope | None) -> AccessScope | None:
        is_global = self.cleaned_data.get('scope_is_global', False)
        roles = self.cleaned_data.get('scope_roles') or []
        departments = self.cleaned_data.get('scope_departments') or []
        users = self.cleaned_data.get('scope_users') or []

        # Пустая матрица — зону не храним (видно по папке / всем).
        if not roles and not departments and not users:
            if existing is not None:
                existing.delete()
            return None

        scope = existing or AccessScope(name=name)
        scope.name = name
        scope.is_global = bool(is_global)
        scope.roles = list(roles)
        scope.save()
        scope.departments.set(departments)
        scope.users.set(users)
        return scope


class FolderAccessForm(_AccessScopeFormBase):
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
        queryset=Department.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': 8}),
    )
    scope_users = forms.ModelMultipleChoiceField(
        label='Пользователи',
        queryset=UserAccount.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': 8}),
    )

    def __init__(self, folder, *args, **kwargs):
        self.folder = folder
        super().__init__(*args, **kwargs)
        self.fields['scope_departments'].queryset = (
            Department.objects.select_related('company').order_by('name')
        )
        self.fields['scope_users'].queryset = (
            UserAccount.objects.filter(is_active=True).order_by('username')
        )
        self._load_scope_initial(folder.access_scope)
        if not folder.access_scope_id:
            self.fields['scope_is_global'].initial = False

    def save(self):
        scope = self._save_scope(
            name=f'{self.folder.name}',
            existing=self.folder.access_scope,
        )
        self.folder.access_scope = scope
        self.folder.save(update_fields=['access_scope'])
        return scope


class DocumentAccessForm(_AccessScopeFormBase):
    """Видимость карточки документооборота: всем / роли / отделы / пользователи."""

    scope_is_global = forms.BooleanField(
        label='Виден всем (у кого есть доступ к папке)',
        required=False,
        initial=True,
    )
    scope_roles = forms.MultipleChoiceField(
        label='Роли',
        choices=ROLE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    scope_departments = forms.ModelMultipleChoiceField(
        label='Отделы',
        queryset=Department.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': 8}),
    )
    scope_users = forms.ModelMultipleChoiceField(
        label='Пользователи',
        queryset=UserAccount.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': 8}),
    )

    def __init__(self, document, *args, **kwargs):
        self.document = document
        super().__init__(*args, **kwargs)
        self.fields['scope_departments'].queryset = (
            Department.objects.select_related('company').order_by('name')
        )
        self.fields['scope_users'].queryset = (
            UserAccount.objects.filter(is_active=True).order_by('username')
        )
        self._load_scope_initial(document.access_scope)

    def save(self):
        title = (self.document.title or f'document-{self.document.pk}')[:100]
        scope = self._save_scope(
            name=f'Doc: {title}',
            existing=self.document.access_scope,
        )
        self.document.access_scope = scope
        self.document.save(update_fields=['access_scope'])
        return scope
