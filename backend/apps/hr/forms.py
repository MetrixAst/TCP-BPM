from django import forms
from betterforms.multiform import MultiForm
from addits.forms import CustomModelForm

from account.forms import UserAccountForm, EmployeeForm
from account.models import Department, Employee

from documents.forms import PaginatorForm
from addits.forms import Select2FieldDefault, Select2ChoiceField

from .models import CalendarItem, Position, LeaveRequest, LeaveType, EmployeeDocument, EmployeeWorkPermit, EmployeeCertification
from .enums import EmployeeStatusEnum, LeaveStatusEnum, DocumentTypeEnum, CertificationStatusEnum, DocumentStatusEnum



ALLOWED_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png', 'docx']
MAX_FILE_SIZE = 10 * 1024 * 1024  


class CalendarItemForm(CustomModelForm):

    start_date = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker'}))
    end_date = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker'}))

    # def clean_category(self):
    #     category = self.cleaned_data["category"]
    #     return category

    class Meta:
        model = CalendarItem
        fields = ('user', 'title', 'start_date', 'end_date', 'category')



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


class CertificationFilterForm(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Поиск'}),
        required=False,
    )
    department = Select2FieldDefault(
        queryset=Department.objects.all(), placeholder='Отдел', required=False,
    )
    cert_type = Select2FieldDefault(queryset=None, placeholder='Тип сертификации', required=False)
    status = Select2ChoiceField(
        choices=[('', 'Статус'), ('active', 'Активна'), ('expired', 'Истекла'), ('pending', 'Ожидает')],
        required=False,
        placeholder='Статус',
    )
    expiring_soon = forms.BooleanField(required=False, label='Истекающие (30 дней)')
    expired = forms.BooleanField(required=False, label='Просроченные')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import CertificationType
        self.fields['cert_type'].queryset = CertificationType.objects.all()
