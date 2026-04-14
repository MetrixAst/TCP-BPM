from django import forms
from .models import FinanceItem


class FinanceItemForm(forms.ModelForm):

    def clean_category(self):
        category = self.cleaned_data["category"]
        return category
    

    class Meta:
        model = FinanceItem
        fields = ('title', 'text', 'date', 'category')
