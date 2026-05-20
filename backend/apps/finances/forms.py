from django import forms
from .models import FinanceItem, GeneratedInvoice, GeneratedInvoiceItem


class FinanceItemForm(forms.ModelForm):

    def clean_category(self):
        category = self.cleaned_data["category"]
        return category

    class Meta:
        model = FinanceItem
        fields = ('title', 'text', 'date', 'category')


class GeneratedInvoiceForm(forms.ModelForm):
    class Meta:
        model = GeneratedInvoice
        fields = [
            'tenant', 'counterparty', 'number',
            'period', 'contract_number',
            'total_amount', 'vat_amount', 'comment',
            'sent_via',
        ]
        widgets = {
            'period': forms.DateInput(attrs={'class': 'form-control single_date_picker'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class GeneratedInvoiceItemForm(forms.ModelForm):
    class Meta:
        model = GeneratedInvoiceItem
        fields = ['name', 'quantity', 'unit', 'price', 'vat_rate']


GeneratedInvoiceItemFormSet = forms.inlineformset_factory(
    GeneratedInvoice,
    GeneratedInvoiceItem,
    form=GeneratedInvoiceItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
