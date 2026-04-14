from django import forms
from addits.forms import Select2FieldDefault, UserSelect2Field, UserSelect2MultipleField, TreeField

from purchases.models import Supplier

from addits.forms import CustomModelForm
from .models import Requistion


class GuestRequistionInitForm(CustomModelForm):

    class Meta:
        model = Requistion
        fields = ('requistion_type', )


class RequistionInitForm(CustomModelForm):

    coordinators = UserSelect2MultipleField(required=True, placeholder="Согласующие")
    observers = UserSelect2MultipleField(required=True, placeholder="Наблюдатели")

    class Meta:
        model = Requistion
        fields = ('requistion_type', 'supplier', 'status', 'number', 'coordinators', 'observers', )


class RequistionForm1(CustomModelForm):

    start_date = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker'}), label='Дата начала')
    start_time = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control time-picker', 'outer_container': 'time-picker-container'}), label='Время')

    class Meta:
        model = Requistion
        fields = ('room', 'route', 'prop_list', 'people_list', 'name', 'role', 'phone', 'start_date', 'start_time', )



class RequistionForm2(CustomModelForm):

    class Meta:
        model = Requistion
        fields = ('name', 'role', 'phone', 'address', 'iin')




class RequistionEditForm(CustomModelForm):

    coordinators = UserSelect2MultipleField(required=True, placeholder="Согласующие")
    observers = UserSelect2MultipleField(required=True, placeholder="Наблюдатели")

    class Meta:
        model = Requistion
        fields = ('status', 'number')