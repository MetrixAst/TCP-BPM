from django.shortcuts import render

from account.role_permissions import need_permission, PermissionEnums


@need_permission(PermissionEnums.REPORTS)
def reports(request):
    kpi_cards = [
        {'label': 'Сумма продаж', 'icon': 'bi-graph-up-arrow', 'color': 'blue'},
        {'label': 'Количество продаж', 'icon': 'bi-receipt', 'color': 'green'},
        {'label': 'Средний чек', 'icon': 'bi-calculator', 'color': 'purple'},
        {'label': 'Посетителей', 'icon': 'bi-people', 'color': 'orange'},
        {'label': 'Конверсия', 'icon': 'bi-percent', 'color': 'teal'},
        {'label': 'Коммунальные услуги', 'icon': 'bi-droplet-half', 'color': 'red'},
    ]
    return render(request, 'site/dashboard/statistic.html', {
        'kpi_cards': kpi_cards,
        'has_analytics_data': False,
    })
