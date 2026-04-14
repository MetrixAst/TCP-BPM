from django.shortcuts import redirect, render

def home(request):
    context = {

    }

    return render(request, 'site/ecopark/ecopark.html', context)



def item(request, pk):
    context = {

    }

    return render(request, 'site/ecopark/ecopark_item.html', context)



def create(request):
    context = {

    }

    return render(request, 'site/ecopark/ecopark_create.html', context)