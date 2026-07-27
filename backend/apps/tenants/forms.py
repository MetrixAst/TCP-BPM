from django import forms
from django.db import transaction

from .models import Tenant, TenantCategory, Room


class TenantForm(forms.ModelForm):
    room = forms.CharField(
        label="Помещение", required=True,
        widget=forms.TextInput(attrs={'class': 'tenant-form-input', 'placeholder': 'Номер помещения'})
    )
    category = forms.CharField(
        label="Категория", required=False,
        widget=forms.TextInput(attrs={'class': 'tenant-form-input', 'placeholder': 'Категория'})
    )

    class Meta:
        model = Tenant
        fields = [
            'name', 'area', 'price', 'discount',
            'phone', 'email', 'address', 'contact',
            'start_date', 'end_date', 'discount_date',
            'percent', 'increase_type', 'note',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'tenant-form-input', 'placeholder': 'Название арендатора'}),
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

        if self.instance and self.instance.pk:
            if self.instance.room_id:
                self.fields['room'].initial = self.instance.room.number
            if self.instance.category_id:
                self.fields['category'].initial = self.instance.category.title

        for field_name in ('name', 'area', 'price'):
            self.fields[field_name].required = True

        for field_name in ('phone', 'email', 'address', 'contact',
                           'start_date', 'end_date', 'discount_date', 'increase_type',
                           'discount', 'percent'):
            self.fields[field_name].required = False
        for field_name in ('start_date', 'end_date', 'discount_date'):
            self.fields[field_name].input_formats = ['%Y-%m-%d', '%d.%m.%Y']

    @transaction.atomic
    def save(self, commit=True):
        instance = super().save(commit=False)

        room_number = (self.cleaned_data.get('room') or '').strip()
        if room_number:
            room_obj, _ = Room.objects.get_or_create(
                number=room_number,
                defaults={'map_id': room_number, 'floor': 0},
            )
            instance.room = room_obj
        else:
            instance.room = None

        category_title = (self.cleaned_data.get('category') or '').strip() or 'Прочее'
        category_obj = TenantCategory.objects.filter(
            title__iexact=category_title
        ).first()
        if category_obj is None:
            category_obj = TenantCategory.objects.create(title=category_title)
        instance.category = category_obj

        if commit:
            instance.save()
        return instance
