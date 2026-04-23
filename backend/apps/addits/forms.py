from django import forms
from account.models import UserAccount
from mptt.forms import TreeNodeChoiceField
from django.forms.widgets import Textarea


class Select2ChoiceField(forms.ChoiceField):
    def __init__(self, choices, required = False, placeholder=""):
        choices.insert(0, ('', '----'))
        super().__init__(choices=choices, required=required, widget=forms.Select(attrs={'class': 'select2', 'placeholder': placeholder}))


class TreeField(TreeNodeChoiceField):
    def __init__(self, queryset, required):
        super().__init__(queryset, required=required, widget=forms.Select(attrs={'class': 'select2',}), empty_label="")


class Select2FieldDefault(forms.ModelChoiceField):
    def __init__(self, queryset, required = False, placeholder=""):
        super().__init__(queryset, required=required, widget=forms.Select(attrs={'class': 'select2', 'placeholder': placeholder}), empty_label="")
    
    # def clean(self, value):
    #     return value


class Select2MultipleFieldDefault(forms.ModelChoiceField):
    def __init__(self, queryset, required = False, placeholder=""):
        super().__init__(queryset, required=required, widget=forms.SelectMultiple(attrs={'class': 'select2', 'placeholder': placeholder}), empty_label="")


class Select2Field(forms.ModelChoiceField):
    def __init__(self, queryset, url, required=False, placeholder=""):
        super().__init__(
            queryset=queryset,
            required=required,
            widget=forms.Select(attrs={
                'class': 'select2_ajax',
                'data-url': url,
                'placeholder': placeholder
            }),
            empty_label=""
        )


class Select2MultipleField(forms.ModelMultipleChoiceField):
    def __init__(self, queryset, url, required=False, placeholder=""):
        super().__init__(
            queryset=queryset,
            required=required,
            widget=forms.SelectMultiple(attrs={
                'class': 'select2_ajax',
                'data-url': url,
                'placeholder': placeholder
            })
        )


class UserSelect2Field(Select2Field):
    def __init__(self, required=False, all=False, placeholder=""):
        selection = 'all' if all else 'self'
        super().__init__(
            queryset=UserAccount.objects.all(),
            url=f'/account/ajax/users/{selection}',
            required=required,
            placeholder=placeholder
        )


class UserSelect2MultipleField(Select2MultipleField):
    def __init__(self, required=False, all=False, placeholder=""):
        selection = 'all' if all else 'self'
        super().__init__(
            queryset=UserAccount.objects.all(),
            url=f'/account/ajax/users/{selection}',
            required=required,
            placeholder=placeholder
        )




class CustomModelForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(CustomModelForm, self).__init__(*args, **kwargs)
        for visible in self.visible_fields():
            existing_classes = visible.field.widget.attrs.get('class', '')
            
            if isinstance(visible.field.widget, Textarea):
                new_class = f"{existing_classes} form-control".strip()
                visible.field.widget.attrs['class'] = new_class
                visible.field.widget.attrs['rows'] = '3'
            
            elif (getattr(visible.field.widget, 'input_type', None) == 'select' or 
                  isinstance(visible.field.widget, forms.Select)):
                visible.field.empty_label = ""
                new_class = f"{existing_classes} select2".strip()
                visible.field.widget.attrs['class'] = new_class
            
            else:
                if 'form-control' not in existing_classes:
                    new_class = f"{existing_classes} form-control".strip()
                    visible.field.widget.attrs['class'] = new_class

            placeholder = visible.field.widget.attrs.get('placeholder', "")
            if placeholder:
                visible.label = placeholder
            elif not visible.label:
                visible.label = visible.field.label