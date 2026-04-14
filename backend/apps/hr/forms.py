from django import forms
from betterforms.multiform import MultiForm
from addits.forms import CustomModelForm

from account.forms import UserAccountForm, EmployeeForm
from account.models import Department

from documents.forms import PaginatorForm
from addits.forms import Select2FieldDefault, Select2ChoiceField

from .models import CalendarItem

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
    ordering = Select2ChoiceField(ORDERING, required=False, placeholder='Сортировка')
    job_title = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control', 'placeholder': 'Должность'}), required=False)
