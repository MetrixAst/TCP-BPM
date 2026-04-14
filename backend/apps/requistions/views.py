from django.shortcuts import redirect, render

from project.paginator import CustomPaginator

from .forms import GuestRequistionInitForm, RequistionInitForm, RequistionForm1, RequistionForm2, RequistionEditForm
from .models import Requistion
from .enums import RequstionTypesEnum

def items(request):
    
    queryset = Requistion.get_available_queryset(request)
    page = request.GET.get('page', 1)

    paginator = CustomPaginator(queryset, page)

    context = {
        'paginator': paginator,
    }

    return render(request, 'site/requistions/requistions.html', context)



def item(request, pk):

    current = Requistion.get_by_id(request, pk)
    arr = current.get_data()
    
    context = {
        'info': arr,
        'current': current,
        'actions': current.actions(request),
    }

    return render(request, 'site/requistions/requistion.html', context)



def item_print(request, pk):

    current = Requistion.get_by_id(request, pk)
    arr = current.get_data()
    
    context = {
        'info': arr,
        'current': current,
    }

    return render(request, 'site/requistions/print.html', context)


def requistion_action(request, pk):
    current = Requistion.get_by_id(request, pk)

    action = request.POST.get('action', None)
    text = request.POST.get('text', None)

    if action == "cancel":
        current.delete()
        return redirect('requistions:home')
    
    current.set_action(request, action, text)

    return redirect('requistions:item', pk=pk)


def create_init(request):

    if request.user.role == "guest":
        form = GuestRequistionInitForm(request.POST or None)
    else:
        form = RequistionInitForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            new = form.save(commit=False)
            new.user = request.user
            
            new.save()
            form.save_m2m()

            if new.status is None or new.status == "": #if is NEW
                new.set_action(request, "create")
            
            return redirect('requistions:create_info', pk=new.id)

    context = {
        'form': form,
    }

    return render(request, 'site/requistions/create.html', context)



def create_info(request, pk):

    instance = Requistion.get_by_id(request, pk)

    if instance.requistion_type in [RequstionTypesEnum.PERM_PASS.value[0], RequstionTypesEnum.TEMP_PASS.value[0]]:
        form = RequistionForm2(request.POST or None, instance=instance)
    else:
        form = RequistionForm1(request.POST or None, instance=instance)

    if request.method == 'POST':
        if form.is_valid():
            form.save()
            
            return redirect('requistions:home')

    context = {
        'form': form,
    }

    return render(request, 'site/requistions/create_info.html', context)


def edit(request, pk):
    
    instance = Requistion.get_by_id(request, pk)

    form = RequistionEditForm(request.POST or None, instance=instance)

    if request.method == 'POST':
        if form.is_valid():
            form.save()
            
            return redirect('requistions:item', pk=pk)

    context = {
        'form': form,
    }

    return render(request, 'site/requistions/edit_requistion.html', context)