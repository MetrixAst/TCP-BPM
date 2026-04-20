from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, PasswordChangeForm
from django.core.exceptions import ValidationError 

from addits.forms import CustomModelForm
from hr.models import Position
from .models import UserAccount, Employee


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


class UserAccountForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super(UserAccountForm, self).__init__(*args, **kwargs)
        for visible in self.visible_fields():
            if visible.field.widget.input_type == 'select':
                visible.field.empty_label = ""
                visible.field.widget.attrs['class'] = 'select2'
            elif visible.field.widget.attrs.get('class') is None:
                visible.field.widget.attrs['class'] = 'form-control'

    class Meta:
        model = UserAccount
        fields = ("username", "password1", "password2", "role", "first_name")


class EditProfileForm(CustomModelForm):
    birthday = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker', 'placeholder': 'День рождения'}))

    class Meta:
        model = UserAccount
        fields = ("first_name", "last_name", "username", "birthday", "gender", "email")


class EmployeeForm(CustomModelForm):
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
        
        select_configs = {
            'department': 'Выберите отдел',
            'position': 'Выберите должность',
            'supervisor': 'Выберите руководителя',
            'status': 'Выберите статус',
        }
        
        for field_name, placeholder in select_configs.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({
                    'class': 'select2',
                    'data-placeholder': placeholder,
                    'data-allow-clear': 'true' 
                })
        
        if 'head' in self.fields:
            self.fields['head'].widget.attrs.update({'class': 'form-check-input'})


class EmployeeAdminForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = '__all__'
    
    def clean_iin(self):
        return validate_iin_logic(self.cleaned_data.get('iin'))