from django import forms
from addits.forms import Select2FieldDefault, UserSelect2Field, UserSelect2MultipleField, TreeField
from purchases.models import Supplier

from .models import Document, Folder, InnerDocument

class PaginatorForm(forms.Form):
    page = forms.IntegerField(widget=forms.HiddenInput(), required=False, initial=1)

    

class DocumentForm(forms.ModelForm):

    title = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control'}))
    number = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control'}))
    reg_date = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker'}))
    text = forms.CharField(widget=forms.Textarea(attrs={'class':'form-control', 'rows': 4}))

    days = forms.IntegerField(initial=4, widget=forms.NumberInput(attrs={'class': 'form-control'}))

    document = forms.FileField(widget=forms.FileInput(attrs={'class':'form-control'}))

    coordinators = UserSelect2MultipleField(required=True)
    observers = UserSelect2MultipleField(required=True)

    # folder = Select2FieldDefault(Folder.get_by_root_type('documents'), required=True)
    folder = TreeField(Folder.objects.none(), required=True)

    need_all = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)
    need_head = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)

    supplier = Select2FieldDefault(queryset=Supplier.objects.all(), required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['folder'].queryset = Folder.get_by_root_type('documents') or Folder.objects.none()

    class Meta:
        model = Document
        fields = ('title', 'number', 'text', 'days', 'coordinators', 'observers', 'need_all', 'need_head', 'supplier', 'reg_date', 'document', 'folder')



class InnerDocumentForm(forms.ModelForm):

    title = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control', 'placeholder': 'Заголовок'}))
    document = forms.FileField(widget=forms.FileInput(attrs={'class':'form-control'}))

    class Meta:
        model = InnerDocument
        fields = ('title', 'document')




class PurchaseForm(forms.ModelForm):

    title = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control'}))
    number = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control'}))
    reg_date = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker'}))

    days = forms.IntegerField(initial=4, widget=forms.NumberInput(attrs={'class': 'form-control'}))

    document = forms.FileField(widget=forms.FileInput(attrs={'class':'form-control'}))

    coordinators = UserSelect2MultipleField(required=True)
    observers = UserSelect2MultipleField(required=True)

    folder = TreeField(Folder.objects.none(), required=True)

    need_all = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)
    need_head = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)

    supplier = Select2FieldDefault(queryset=Supplier.objects.all(), required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['folder'].queryset = Folder.get_by_root_type('purchases') or Folder.objects.none()

    class Meta:
        model = Document
        fields = ('title', 'number', 'coordinators', 'observers', 'need_all', 'need_head', 'supplier', 'reg_date', 'document', 'folder')



class BudgetForm(forms.ModelForm):

    title = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control'}))
    number = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control'}))
    reg_date = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker'}))

    document = forms.FileField(widget=forms.FileInput(attrs={'class':'form-control'}))

    coordinators = UserSelect2MultipleField(required=True)
    observers = UserSelect2MultipleField(required=True)

    class Meta:
        model = Document
        fields = ('title', 'number', 'coordinators', 'observers', 'reg_date', 'document')

    def save(self, commit: bool = ...):
        res = super().save(commit)
        res.folder = Folder.objects.get(root_type='budget')

        return res



class DocumentsForm(PaginatorForm):
    
    search = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control', 'placeholder': 'Поиск'}), required=False)
    supplier = Select2FieldDefault(queryset=Supplier.objects.all(), placeholder='Контрагент', required=False)
    date = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker', 'placeholder': 'Дата'}), required=False)
    coordinator = UserSelect2Field(all=True, required=False, placeholder='Ответственный')

