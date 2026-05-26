from django import forms

from .models import Counterparty


class CounterpartyForm(forms.ModelForm):
    class Meta:
        model = Counterparty
        fields = (
            'full_name',
            'short_name',
            'bin_number',
            'iin',
            'address',
            'phone',
            'email',
            'is_supplier',
            'is_customer',
        )
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Полное наименование'}),
            'short_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Краткое название'}),
            'bin_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12 цифр'}),
            'iin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ИИН (для ИП)'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_supplier': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_customer': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.id_1c:
            import uuid
            instance.id_1c = f'bpm-{uuid.uuid4().hex[:12]}'
        if commit:
            instance.save()
            self.save_m2m()
        return instance
