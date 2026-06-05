from django import forms

from addits.forms import UserSelect2Field, UserSelect2MultipleField, Select2ChoiceField, Select2Field
from account.services.access_scope import filter_counterparties_queryset
from onec.models import Counterparty
from .models import Task
from .enums import TaskTypeEnum


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

    task_type = Select2ChoiceField(
        choices=[("", "Тип задачи")] + TaskTypeEnum.list(),
        required=True,
        placeholder="Тип задачи"
    )

    counterparty = Select2Field(
        queryset=Counterparty.objects.none(),
        url='/onec/api/cp-search/',
        required=False,
        placeholder="Контрагент",
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
            "task_type",
            "counterparty",
        )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user is not None:
            self.fields['counterparty'].queryset = filter_counterparties_queryset(
                Counterparty.objects.all(),
                user,
            ).order_by('short_name')

        placeholders = {
            "executor": "Исполнитель",
            "co_executors": "Соисполнители",
            "observers": "Наблюдатели",
            "priority": "Приоритет",
            "task_type": "Тип задачи",
            "counterparty": "Контрагент",
        }

        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs.update({
                "class": "task-edit-select",
                "data-placeholder": placeholder,
            })