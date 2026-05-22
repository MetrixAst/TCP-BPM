from django import forms
from addits.forms import UserSelect2Field, UserSelect2MultipleField, Select2ChoiceField
from .models import Task


class TaskForm(forms.ModelForm):
    title = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "task-edit-control",
            "placeholder": "Название задачи",
        })
    )

    deadline = forms.DateField(
        input_formats=["%d.%m.%Y", "%Y-%m-%d"],
        widget=forms.DateInput(
            format="%d.%m.%Y",
            attrs={
                "class": "task-edit-control task-edit-date",
                "placeholder": "дд.мм.гггг",
                "autocomplete": "off",
            }
        )
    )

    text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "task-edit-control task-edit-control--textarea",
            "placeholder": "Описание",
            "rows": 4,
        })
    )

    executor = UserSelect2Field(required=True, all=True)
    co_executors = UserSelect2MultipleField(required=False, all=True)
    observers = UserSelect2MultipleField(required=False, all=True)

    priority = Select2ChoiceField(
        choices=[("", "Приоритет")] + Task.PRIORITIES.copy(),
        required=True,
        placeholder="Приоритет"
    )

    class Meta:
        model = Task
        fields = (
            "executor",
            "co_executors",
            "observers",
            "deadline",
            "title",
            "text",
            "priority",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        placeholders = {
            "executor": "Исполнитель",
            "co_executors": "Соисполнители",
            "observers": "Наблюдатели",
            "priority": "Приоритет",
        }

        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs.update({
                "class": "task-edit-select",
                "data-placeholder": placeholder,
            })