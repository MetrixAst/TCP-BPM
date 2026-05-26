from django import forms

from .models import Tenant, TenantCategory, Room


class TenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = [
            'name', 'category', 'room', 'area', 'price', 'discount',
            'phone', 'email', 'address', 'contact',
            'start_date', 'end_date', 'discount_date',
            'percent', 'increase_type', 'note',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'tenant-form-input', 'placeholder': 'Название арендатора'}),
            'category': forms.Select(attrs={'class': 'tenant-form-input'}),
            'room': forms.Select(attrs={'class': 'tenant-form-input'}),
            'area': forms.NumberInput(attrs={'class': 'tenant-form-input', 'step': '0.01', 'min': '0'}),
            'price': forms.NumberInput(attrs={'class': 'tenant-form-input', 'step': '0.01', 'min': '0'}),
            'discount': forms.NumberInput(attrs={'class': 'tenant-form-input', 'min': '0', 'max': '100'}),
            'phone': forms.TextInput(attrs={'class': 'tenant-form-input', 'placeholder': '+7 700 000 00 00'}),
            'email': forms.EmailInput(attrs={'class': 'tenant-form-input', 'placeholder': 'email@example.kz'}),
            'address': forms.TextInput(attrs={'class': 'tenant-form-input', 'placeholder': 'Адрес'}),
            'contact': forms.TextInput(attrs={'class': 'tenant-form-input', 'placeholder': 'ФИО ответственного'}),
            'start_date': forms.DateInput(attrs={'class': 'tenant-form-input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'tenant-form-input', 'type': 'date'}),
            'discount_date': forms.DateInput(attrs={'class': 'tenant-form-input', 'type': 'date'}),
            'percent': forms.NumberInput(attrs={'class': 'tenant-form-input', 'min': '0', 'max': '100'}),
            'increase_type': forms.Select(attrs={'class': 'tenant-form-input'}),
            'note': forms.Textarea(attrs={'class': 'tenant-form-input tenant-form-input--textarea', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = TenantCategory.objects.all()
        self.fields['category'].required = False
        self.fields['category'].empty_label = '— Выберите категорию —'

        self.fields['room'].queryset = Room.objects.all()
        self.fields['room'].required = False
        self.fields['room'].empty_label = '— Без помещения —'

        for field_name in ('name', 'area', 'price', 'phone', 'email', 'address', 'contact',
                           'start_date', 'end_date', 'discount_date', 'increase_type'):
            self.fields[field_name].required = True

    def clean_category(self):
        category = self.cleaned_data.get('category')
        if category:
            return category
        category, _ = TenantCategory.objects.get_or_create(title='Прочее')
        return category
