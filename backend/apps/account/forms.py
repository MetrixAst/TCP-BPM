from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, PasswordChangeForm
from django.core.exceptions import ValidationError 

from addits.forms import CustomModelForm
import re

from hr.models import Position
from .models import UserAccount, Employee
from hr.enums import EmployeeStatusEnum
ROLE_PICK_NEW = '__new_role__'


def validate_iin_logic(iin):
    if not iin:
        raise ValidationError("ИИН обязателен для заполнения.")
    if not iin.isdigit():
        raise ValidationError("ИИН должен содержать только цифры.")
    if len(iin) != 12:
        raise ValidationError("ИИН должен состоять ровно из 12 цифр.")
    return iin


class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={"autofocus": True, "class": 'form-control', "placeholder": 'Введите логин'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": 'form-control', "placeholder": 'Введите пароль', "autocomplete": "current-password"}))


class CustomPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(widget=forms.PasswordInput(attrs={"class": 'form-control'}), label="Старый пароль")
    new_password1 = forms.CharField(widget=forms.PasswordInput(attrs={"class": 'form-control'}), label="Новый пароль")
    new_password2 = forms.CharField(widget=forms.PasswordInput(attrs={"class": 'form-control'}), label="Повторите новый пароль")


class EmployeeChoiceField(forms.ModelChoiceField):
    """Руководитель и др.: ФИО и должность, не логин."""

    def label_from_instance(self, obj):
        return obj.get_display_with_position()


class UserAccountForm(UserCreationForm):
    role_pick = forms.ChoiceField(
        label='Роль',
        choices=[],
        widget=forms.Select(attrs={'class': 'select2', 'id': 'id_role_pick'}),
    )
    role_custom = forms.CharField(
        label='Код новой роли',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'например warehouse_manager',
            'id': 'id_role_custom',
        }),
        help_text='Латиница и подчёркивания. Роль должна быть настроена в системе прав.',
    )

    class Meta:
        model = UserAccount
        fields = ("username", "password1", "password2", "first_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        role_choices = list(UserAccount.ROLES) + [(ROLE_PICK_NEW, '— Ввести новую роль —')]
        self.fields['role_pick'].choices = role_choices

        initial_role = None
        if self.instance and self.instance.pk:
            initial_role = self.instance.role
        elif self.is_bound:
            initial_role = self.data.get('role') or self.data.get('role_pick')
        if initial_role and initial_role != ROLE_PICK_NEW:
            known = {c[0] for c in UserAccount.ROLES}
            if initial_role in known:
                self.fields['role_pick'].initial = initial_role
            else:
                self.fields['role_pick'].initial = ROLE_PICK_NEW
                self.fields['role_custom'].initial = initial_role

        for visible in self.visible_fields():
            if visible.field.widget.input_type == 'select':
                visible.field.empty_label = ""
                if 'class' not in visible.field.widget.attrs:
                    visible.field.widget.attrs['class'] = 'select2'
            elif visible.field.widget.attrs.get('class') is None:
                visible.field.widget.attrs['class'] = 'form-control'

    def clean(self):
        cleaned = super().clean()
        pick = cleaned.get('role_pick')
        custom = (cleaned.get('role_custom') or '').strip().lower()

        if pick == ROLE_PICK_NEW:
            if not custom:
                self.add_error('role_custom', 'Укажите код новой роли.')
                return cleaned
            if not re.match(r'^[a-z][a-z0-9_]*$', custom):
                self.add_error(
                    'role_custom',
                    'Код роли: латинские буквы, цифры и подчёркивания (начинается с буквы).',
                )
                return cleaned
            known = {c[0] for c in UserAccount.ROLES}
            if custom not in known:
                self.add_error(
                    'role_custom',
                    f'Роль «{custom}» не найдена. Доступные: {", ".join(sorted(known))}.',
                )
                return cleaned
            cleaned['role'] = custom
        elif pick:
            cleaned['role'] = pick
        return cleaned

    def save(self, commit=True):
        self.instance.role = self.cleaned_data['role']
        return super().save(commit=commit)


class EditProfileForm(CustomModelForm):
    birthday = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker', 'placeholder': 'День рождения'}))

    class Meta:
        model = UserAccount
        fields = ("first_name", "last_name", "username", "birthday", "gender", "email")


class EmployeeForm(CustomModelForm):
    position = forms.ModelChoiceField(
        queryset=Position.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'select2', 'data-placeholder': 'Выберите должность'}),
    )
    supervisor = EmployeeChoiceField(
        queryset=Employee.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'select2', 'data-placeholder': 'Выберите руководителя'}),
    )
    iin = forms.CharField(
        label="ИИН",
        min_length=12, 
        max_length=12,
        required=True, 
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ИИН (12 цифр)'})
    )
    hire_date = forms.DateField(
        widget=forms.TextInput(attrs={'class':'form-control single_date_picker', 'placeholder': 'Дата приема'}),
        required=False
    )
    phone = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Телефон'}), required=False)
    personal_email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Личная почта'}), required=False)

    class Meta:
        model = Employee
        fields = (
            'department', 'position', 'supervisor', 'status', 
            'iin', 'hire_date', 'phone', 'personal_email', 'head'
        )

    def clean_iin(self):
        return validate_iin_logic(self.cleaned_data.get('iin'))

    def clean(self):
        cleaned_data = super().clean()
        department = cleaned_data.get("department")
        position = cleaned_data.get("position")

        if department and position:
            if position.department != department:
                self.add_error('position', f"Выбранная должность '{position}' не принадлежит отделу '{department}'.")
        
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        dept_id = None
        if self.is_bound:
            dept_id = self.data.get(self.add_prefix('department'))
        elif self.instance and self.instance.pk and self.instance.department_id:
            dept_id = self.instance.department_id

        if dept_id:
            self.fields['position'].queryset = Position.objects.filter(
                department_id=dept_id,
            ).order_by('title')
        else:
            self.fields['position'].queryset = Position.objects.none()

        supervisor_qs = Employee.objects.filter(
            status=EmployeeStatusEnum.ACTIVE,
        ).select_related('user', 'position', 'department').order_by(
            'user__last_name', 'user__first_name', 'user__username',
        )
        if self.instance and self.instance.pk:
            supervisor_qs = supervisor_qs.exclude(pk=self.instance.pk)
        self.fields['supervisor'].queryset = supervisor_qs

        select_configs = {
            'department': 'Выберите отдел',
            'status': 'Выберите статус',
        }

        for field_name, placeholder in select_configs.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({
                    'class': 'select2',
                    'data-placeholder': placeholder,
                    'data-allow-clear': 'true',
                })

        if 'position' in self.fields:
            self.fields['position'].widget.attrs.update({
                'class': 'select2',
                'data-placeholder': 'Выберите должность',
                'data-allow-clear': 'true',
            })
        if 'supervisor' in self.fields:
            self.fields['supervisor'].widget.attrs.update({
                'data-allow-clear': 'true',
            })

        if 'head' in self.fields:
            self.fields['head'].widget.attrs.update({'class': 'form-check-input'})


class EmployeeAdminForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = '__all__'
    
    def clean_iin(self):
        return validate_iin_logic(self.cleaned_data.get('iin'))
