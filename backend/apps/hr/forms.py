from django import forms
from betterforms.multiform import MultiForm
from addits.forms import CustomModelForm

from account.forms import UserAccountForm, EmployeeForm
from account.models import Department, Employee

from documents.forms import PaginatorForm
from addits.forms import Select2FieldDefault, Select2ChoiceField

from .models import CalendarItem
from .models import Position

from .enums import EmployeeStatusEnum 


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


