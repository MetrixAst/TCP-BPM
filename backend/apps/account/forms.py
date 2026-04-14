from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, PasswordChangeForm

from addits.forms import CustomModelForm

from .models import UserAccount, Employee

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
    


class EmployeeForm(CustomModelForm):

    head = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)

    class Meta:
        model = Employee
        fields = ('department', 'head', 'job_title')


class EditProfileForm(CustomModelForm):

    birthday = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker', 'placeholder': 'День рождения'}))

    class Meta:
        model = UserAccount
        fields = ("first_name", "last_name", "username", "birthday", "gender", "email")