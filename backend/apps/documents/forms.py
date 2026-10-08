from django import forms
from addits.forms import Select2FieldDefault, UserSelect2MultipleField, TreeField
from purchases.models import Supplier

from .models import Document, Folder, InnerDocument
from .folder_structure import ensure_folder_tree


def all_folders_queryset(document_type):
    """Все папки указанного типа (включая вложенные) — для выбора при создании."""
    try:
        root = ensure_folder_tree(document_type)
        return root.get_descendants(include_self=False)
    except Exception:
        return Folder.objects.none()

class PaginatorForm(forms.Form):
    page = forms.IntegerField(widget=forms.HiddenInput(), required=False, initial=1)

    

class DocumentForm(forms.ModelForm):
    """Загрузка файла в папку документооборота (без маршрута согласования)."""

    title = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название документа'}),
    )
    number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Авто, если пусто'}),
    )
    reg_date = forms.DateField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control single_date_picker'}),
    )
    text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Комментарий (необязательно)'}),
    )
    document = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control'}),
    )
    folder = TreeField(Folder.objects.none(), required=True)

    # Видимость (AccessScope): по умолчанию — всем с доступом к папке
    scope_is_global = forms.BooleanField(
        label='Виден всем (у кого есть доступ к папке)',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    scope_roles = forms.MultipleChoiceField(
        label='Роли',
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    scope_departments = forms.ModelMultipleChoiceField(
        label='Отделы',
        queryset=None,
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': 6}),
    )
    scope_users = forms.ModelMultipleChoiceField(
        label='Пользователи',
        queryset=None,
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': 6}),
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        from account.models import Department, UserAccount

        self.fields['folder'].queryset = all_folders_queryset('documents')
        self.fields['folder'].label = 'Папка'
        self.fields['scope_roles'].choices = UserAccount.ROLES
        self.fields['scope_departments'].queryset = (
            Department.objects.select_related('company').order_by('name')
        )
        self.fields['scope_users'].queryset = (
            UserAccount.objects.filter(is_active=True).order_by('username')
        )
        scope = getattr(self.instance, 'access_scope', None) if self.instance and self.instance.pk else None
        if scope:
            self.fields['scope_is_global'].initial = scope.is_global
            self.fields['scope_roles'].initial = scope.roles or []
            self.fields['scope_departments'].initial = scope.departments.all()
            self.fields['scope_users'].initial = scope.users.all()

    def save_access_scope(self, document: Document):
        """Сохраняет зону видимости после document.save()."""
        from account.models import AccessScope

        is_global = self.cleaned_data.get('scope_is_global', False)
        roles = self.cleaned_data.get('scope_roles') or []
        departments = self.cleaned_data.get('scope_departments') or []
        users = self.cleaned_data.get('scope_users') or []

        existing = document.access_scope
        # Пустая матрица — без зоны: видят все с доступом к папке.
        if not roles and not departments and not users:
            if existing is not None:
                existing.delete()
                document.access_scope = None
                document.save(update_fields=['access_scope'])
            return None

        title = (document.title or f'document-{document.pk}')[:100]
        scope = existing or AccessScope(name=f'Doc: {title}')
        scope.name = f'Doc: {title}'
        scope.is_global = bool(is_global)
        scope.roles = list(roles)
        scope.save()
        scope.departments.set(departments)
        scope.users.set(users)
        document.access_scope = scope
        document.save(update_fields=['access_scope'])
        return scope

    class Meta:
        model = Document
        fields = ('title', 'number', 'text', 'reg_date', 'document', 'folder')



class InnerDocumentForm(forms.ModelForm):

    title = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control', 'placeholder': 'Заголовок'}))
    document = forms.FileField(widget=forms.FileInput(attrs={'class':'form-control'}))

    class Meta:
        model = InnerDocument
        fields = ('title', 'document')




class PurchaseForm(forms.ModelForm):

    title = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control'}))
    number = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control'}))
    reg_date = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker'}))

    days = forms.IntegerField(initial=4, widget=forms.NumberInput(attrs={'class': 'form-control'}))

    document = forms.FileField(widget=forms.FileInput(attrs={'class':'form-control'}))

    coordinators = UserSelect2MultipleField(required=True, all=True, placeholder='Согласующие')
    observers = UserSelect2MultipleField(required=True, all=True, placeholder='Наблюдатели')

    folder = TreeField(Folder.objects.none(), required=True)

    need_all = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)
    need_head = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)

    supplier = Select2FieldDefault(queryset=Supplier.objects.all(), required=True)

    def __init__(self, *args, **kwargs):
        kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['folder'].queryset = all_folders_queryset('purchases')
        self.fields['folder'].label = 'Папка'
        self.fields['document'].label = 'Файл'
        self.fields['title'].label = 'Название документа'
        self.fields['number'].label = 'Номер документа'
        self.fields['reg_date'].label = 'Дата'
        self.fields['days'].label = 'Срок (дней)'
        self.fields['need_all'].label = 'Все согласующие должны согласовать'
        self.fields['need_head'].label = 'Требуется подпись руководителя'
        self.fields['supplier'].label = 'Контрагент'

    class Meta:
        model = Document
        fields = ('title', 'number', 'coordinators', 'observers', 'need_all', 'need_head', 'supplier', 'reg_date', 'document', 'folder')



class BudgetForm(forms.ModelForm):

    title = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control'}))
    number = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control'}))
    reg_date = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker'}))

    document = forms.FileField(widget=forms.FileInput(attrs={'class':'form-control'}))

    coordinators = UserSelect2MultipleField(required=True, all=True, placeholder='Согласующие')
    observers = UserSelect2MultipleField(required=True, all=True, placeholder='Наблюдатели')

    class Meta:
        model = Document
        fields = ('title', 'number', 'coordinators', 'observers', 'reg_date', 'document')

    def save(self, commit: bool = ...):
        res = super().save(commit)
        res.folder = Folder.objects.get(root_type='budget')

        return res


class DocumentsForm(PaginatorForm):
    
    search = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control',}), required=False)
    supplier = Select2FieldDefault(queryset=Supplier.objects.all(), placeholder='Контрагент', required=False)
    date = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker', }), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['search'].label = 'Поиск'
        self.fields['supplier'].label = 'Контрагент'
        self.fields['date'].label = 'Дата'
