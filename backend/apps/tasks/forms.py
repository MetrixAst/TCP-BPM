from django import forms
from addits.forms import UserSelect2Field, UserSelect2MultipleField
from .models import Task
from account.models import UserAccount

class TaskForm(forms.ModelForm):

    title = forms.CharField(widget=forms.TextInput(attrs={'class':'form-control'}))
    deadline = forms.DateField(widget=forms.TextInput(attrs={'class':'form-control single_date_picker'}))
    text = forms.CharField(widget=forms.Textarea(attrs={'class':'form-control', 'rows': 4}))
    important = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)

    responsible = UserSelect2MultipleField(required=True)
    observers = UserSelect2MultipleField(required=True)

    class Meta:
        model = Task
        fields = ('responsible', 'observers', 'deadline', 'title', 'text', 'important', )