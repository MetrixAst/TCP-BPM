from django import forms
from addits.forms import CustomModelForm
from .models import Supplier, Country, City, SupplierCategory
from .enums import SupplierStatusEnum, SupplierCheckedStatusEnum, SupplierFormEnum, SupplierTypeEnum


class SupplierForm(CustomModelForm):

    reg_date = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker'}))

    class Meta:
        model = Supplier
        fields = '__all__'