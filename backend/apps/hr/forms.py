from django import forms
from betterforms.multiform import MultiForm
from addits.forms import CustomModelForm

from account.forms import UserAccountForm, EmployeeForm, EmployeeChoiceField
from account.models import Department, Employee, UserAccount

from documents.forms import PaginatorForm
from addits.forms import Select2FieldDefault, Select2ChoiceField

from .models import CalendarItem, Position, LeaveRequest, LeaveType, EmployeeDocument, EmployeeWorkPermit, EmployeeCertification
from .enums import CalendarItemType, EmployeeStatusEnum, LeaveStatusEnum, DocumentTypeEnum, CertificationStatusEnum, DocumentStatusEnum



ALLOWED_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png', 'docx']
MAX_FILE_SIZE = 10 * 1024 * 1024  


class EmployeeUserChoiceField(forms.ModelChoiceField):
    """Сотрудники в выпадающем списке по ФИО, не по логину."""

    def label_from_instance(self, obj):
        name = (obj.get_name or '').strip()
        if name and name != obj.username:
            label = name
        else:
            label = obj.username
        emp = getattr(obj, 'employee_info', None)
        if emp and emp.position_id:
            label = f'{label} — {emp.position.title}'
        return label


class CalendarItemForm(CustomModelForm):
    category = forms.CharField(widget=forms.HiddenInput(), required=False)

    user = EmployeeUserChoiceField(
        queryset=UserAccount.objects.none(),
        required=True,
        widget=forms.Select(attrs={'class': 'select2', 'data-placeholder': 'Выберите сотрудника'}),
    )

    start_date = forms.DateField(
        input_formats=['%d.%m.%Y', '%Y-%m-%d'],
        widget=forms.TextInput(attrs={
            'class': 'form-control js-cal-date',
            'placeholder': 'дд.мм.гггг',
            'autocomplete': 'off',
        }),
    )
    end_date = forms.DateField(
        input_formats=['%d.%m.%Y', '%Y-%m-%d'],
        widget=forms.TextInput(attrs={
            'class': 'form-control js-cal-date',
            'placeholder': 'дд.мм.гггг',
            'autocomplete': 'off',
        }),
    )
    title = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Город, цель командировки…',
        }),
    )

    class Meta:
        model = CalendarItem
        fields = ('user', 'title', 'start_date', 'end_date', 'category')

    def __init__(self, *args, category=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = (
            UserAccount.objects.filter(
                employee_info__isnull=False,
                is_active=True,
            )
            .select_related('employee_info', 'employee_info__position', 'employee_info__department')
            .order_by('last_name', 'first_name', 'username')
        )
        if category:
            self.fields['category'].initial = category
        elif self.instance.pk:
            self.fields['category'].initial = self.instance.category
        else:
            self.fields['category'].initial = CalendarItemType.SECONDMENT.value[0]

    def clean_category(self):
        category = self.cleaned_data.get('category') or CalendarItemType.SECONDMENT.value[0]
        valid = {c[0] for c in CalendarItemType.list()}
        if category not in valid:
            raise forms.ValidationError('Некорректный тип записи')
        return category



class EmployeeCreationForm(MultiForm):
    form_classes = {
        'user': UserAccountForm,
        'employee': EmployeeForm,
    }



class EmployeesListForm(PaginatorForm):

    ORDERING = [
        ('name', 'По имени'),
        ('department', 'Департамент'),
        ('id', 'По дате добавления'),
    ]
    
    search = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control', 'placeholder': 'Поиск'}), required=False)
    
    department = Select2FieldDefault(queryset=Department.objects.all(), placeholder='Отдел', required=False)
    position = Select2FieldDefault(queryset=Position.objects.all(), placeholder='Должность', required=False)

    status = Select2ChoiceField(
        choices=[('', 'Статус')] + EmployeeStatusEnum.choices, 
        required=False, 
        placeholder='Статус'
    )
    ordering = Select2ChoiceField(ORDERING, required=False, placeholder='Сортировка')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        placeholders = {
            'department': 'Отдел',
            'position': 'Должность',
            'status': 'Статус',
            'ordering': 'Сортировка'
        }
        
        for field_name, text in placeholders.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({
                    'data-allow-clear': 'true',
                    'data-placeholder': text
                })


class LeaveRequestForm(CustomModelForm):
    start_date = forms.DateField(
        widget=forms.TextInput(attrs={
            'class': 'form-control single_date_picker',
            'id': 'id_start_date',
        })
    )
    end_date = forms.DateField(
        widget=forms.TextInput(attrs={
            'class': 'form-control single_date_picker',
            'id': 'id_end_date',
        })
    )

    leave_type = Select2FieldDefault(
        queryset=LeaveType.objects.all(),
        placeholder='Тип отпуска',
        required=True,
    )

    class Meta:
        model = LeaveRequest
        fields = ('leave_type', 'start_date', 'end_date', 'comment')

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_date')
        end = cleaned_data.get('end_date')
        if start and end and start > end:
            raise forms.ValidationError(
                "Дата начала не может быть позже даты окончания"
            )
        return cleaned_data

class LeaveFilterForm(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Поиск по сотруднику',
        }),
        required=False
    )
    department = Select2FieldDefault(
        queryset=Department.objects.all(),
        placeholder='Отдел',
        required=False
    )
    leave_type = Select2FieldDefault(
        queryset=LeaveType.objects.all(),
        placeholder='Тип отпуска',
        required=False
    )
    status = Select2ChoiceField(
        choices=[('', 'Статус')] + LeaveStatusEnum.choices,
        required=False,
        placeholder='Статус'
    )
    date_from = forms.DateField(
        widget=forms.TextInput(attrs={'class': 'form-control single_date_picker'}),
        required=False,
        label='С'
    )
    date_to = forms.DateField(
        widget=forms.TextInput(attrs={'class': 'form-control single_date_picker'}),
        required=False,
        label='По'
    )


def validate_file(file):
    if file:
        ext = file.name.split('.')[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError(f"Недопустимый формат. Разрешены: {', '.join(ALLOWED_EXTENSIONS)}")
        if file.size > MAX_FILE_SIZE:
            raise forms.ValidationError("Файл не должен превышать 10MB")


class EmployeeDocumentForm(forms.ModelForm):
    class Meta:
        model = EmployeeDocument
        fields = ['employee', 'doc_type', 'title', 'version', 'status', 'file', 'signed_at', 'expires_at', 'notes']
        widgets = {
            'signed_at': forms.TextInput(attrs={'class': 'form-control single_date_picker'}),
            'expires_at': forms.TextInput(attrs={'class': 'form-control single_date_picker'}),
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        validate_file(file)
        return file


class DocumentFilterForm(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Поиск'}),
        required=False
    )
    department = Select2FieldDefault(queryset=Department.objects.all(), placeholder='Отдел', required=False)
    doc_type = Select2ChoiceField(
        choices=[('', 'Тип')] + DocumentTypeEnum.choices, required=False, placeholder='Тип'
    )
    status = Select2ChoiceField(
        choices=[('', 'Статус')] + DocumentStatusEnum.choices, required=False, placeholder='Статус'
    )
    expiring_soon = forms.BooleanField(required=False, label='Истекающие (30 дней)')


class EmployeeWorkPermitForm(forms.ModelForm):
    employee = EmployeeChoiceField(
        queryset=Employee.objects.none(),
        widget=forms.Select(attrs={'class': 'select2'}),
    )

    class Meta:
        model = EmployeeWorkPermit
        fields = ['employee', 'category', 'issue_date', 'expiry_date', 'document_number', 'scan']
        widgets = {
            'issue_date': forms.TextInput(attrs={'class': 'form-control single_date_picker'}),
            'expiry_date': forms.TextInput(attrs={'class': 'form-control single_date_picker'}),
        }

    def clean_scan(self):
        file = self.cleaned_data.get('scan')
        validate_file(file)
        return file

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = Employee.objects.filter(
            status=EmployeeStatusEnum.ACTIVE,
        ).select_related('user', 'position', 'department').order_by(
            'user__last_name', 'user__first_name',
        )


class PermitFilterForm(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Поиск'}),
        required=False
    )
    department = Select2FieldDefault(queryset=Department.objects.all(), placeholder='Отдел', required=False)
    category = Select2FieldDefault(queryset=None, placeholder='Категория', required=False)
    expiring_soon = forms.BooleanField(required=False, label='Истекающие (30 дней)')
    expired = forms.BooleanField(required=False, label='Просроченные')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import WorkCategory
        self.fields['category'].queryset = WorkCategory.objects.all()


class EmployeeCertificationForm(forms.ModelForm):
    employee = EmployeeChoiceField(
        queryset=Employee.objects.none(),
        widget=forms.Select(attrs={'class': 'select2'}),
    )

    cert_type = forms.CharField(
        label='Тип сертификации',
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Например: Охрана труда, первая помощь',
        }),
    )

    class Meta:
        model = EmployeeCertification
        fields = ['employee', 'cert_type', 'certificate_number', 'issue_date', 'expiry_date', 'issuing_body', 'scan', 'notes']
        widgets = {
            'issue_date': forms.TextInput(attrs={'class': 'form-control single_date_picker'}),
            'expiry_date': forms.TextInput(attrs={'class': 'form-control single_date_picker'}),
        }

    def clean_scan(self):
        file = self.cleaned_data.get('scan')
        validate_file(file)
        return file

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = Employee.objects.filter(
            status=EmployeeStatusEnum.ACTIVE,
        ).select_related('user', 'position', 'department').order_by(
            'user__last_name', 'user__first_name',
        )


class CertificationFilterForm(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Поиск'}),
        required=False,
    )
    department = Select2FieldDefault(
        queryset=Department.objects.all(), placeholder='Отдел', required=False,
    )
    cert_type = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Тип сертификации'}),
    )
    status = Select2ChoiceField(
        choices=[('', 'Статус'), ('active', 'Активна'), ('expired', 'Истекла'), ('pending', 'Ожидает')],
        required=False,
        placeholder='Статус',
    )
    expiring_soon = forms.BooleanField(required=False, label='Истекающие (30 дней)')
    expired = forms.BooleanField(required=False, label='Просроченные')
