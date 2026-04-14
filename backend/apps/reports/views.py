from django.shortcuts import redirect, render

def reports(request):
    context = {

    }

    return render(request, 'site/dashboard/statistic.html', context)