from django import forms
from addits.forms import UserSelect2Field, UserSelect2MultipleField
from .models import Task


class TaskForm(forms.ModelForm):
    title = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    deadline = forms.DateField(widget=forms.TextInput(attrs={'class': 'form-control single_date_picker'}))
    text = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}))

    executor = UserSelect2Field(required=False)
    co_executors = UserSelect2MultipleField(required=False)
    observers = UserSelect2MultipleField(required=True)

    class Meta:
        model = Task
        fields = ('executor', 'co_executors', 'observers', 'deadline', 'title', 'text', 'priority')