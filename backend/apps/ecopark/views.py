from django.shortcuts import redirect, render


def _fmt_amount(value):
    return f'{int(value):,}'.replace(',', ' ')


def _demo_works():
    return [
        {
            'id': 1,
            'title': 'Замена расходников эскалатора',
            'object': 'Эскалатор',
            'date': '12.11.2024',
            'executor': 'ТОО Cisco',
            'responsible': 'Баянгазиева Алия',
            'amount': 125_430,
            'status': 'done',
            'status_label': 'Выполнен',
        },
        {
            'id': 2,
            'title': 'Проверка насосной станции',
            'object': 'Сантехника',
            'date': '18.01.2025',
            'executor': 'ИП Калиева',
            'responsible': 'Бекбердиев Кайрат',
            'amount': 89_200,
            'status': 'progress',
            'status_label': 'В процессе',
        },
        {
            'id': 3,
            'title': 'Ремонт освещения 1 этажа',
            'object': '1 этаж электроника',
            'date': '05.02.2025',
            'executor': 'ОАО Казахтелеком',
            'responsible': 'Тажиева Оля',
            'amount': 214_800,
            'status': 'pending',
            'status_label': 'Ожидает',
        },
        {
            'id': 4,
            'title': 'Устранение протечки (4 этаж)',
            'object': 'Трубы на 4 этаже',
            'date': '10.03.2025',
            'executor': 'ТОО Рога и копыта',
            'responsible': 'Рашидова Рахиля',
            'amount': 67_500,
            'status': 'overdue',
            'status_label': 'Просрочен',
        },
    ]


def _kpi_from_works(works):
    total = len(works)
    done = sum(1 for w in works if w['status'] == 'done')
    progress = sum(1 for w in works if w['status'] == 'progress')
    total_sum = sum(w['amount'] for w in works)
    return {
        'total': total,
        'done': done,
        'progress': progress,
        'total_sum': total_sum,
        'total_sum_fmt': _fmt_amount(total_sum),
    }


def _enrich_work(work):
    row = dict(work)
    row['amount_fmt'] = _fmt_amount(row['amount'])
    return row


def home(request):
    works = [_enrich_work(w) for w in _demo_works()]
    context = {
        'works': works,
        'kpi': _kpi_from_works(works),
        'objects': sorted({w['object'] for w in works}),
        'executors': sorted({w['executor'] for w in works}),
    }
    return render(request, 'site/ecopark/ecopark.html', context)


def item(request, pk):
    works = {w['id']: _enrich_work(w) for w in _demo_works()}
    work = works.get(pk) or works[1]
    history = [
        {**work, 'date': '15.07.2022 11:51'},
        {**work, 'date': '02.06.2022 09:30', 'amount': 28_100, 'amount_fmt': _fmt_amount(28_100)},
        {**work, 'date': '11.03.2022 14:12', 'amount': 31_200, 'amount_fmt': _fmt_amount(31_200)},
    ]
    context = {
        'work': work,
        'history': history,
    }
    return render(request, 'site/ecopark/ecopark_item.html', context)


def create(request):
    if request.method == 'POST':
        return redirect('ecopark:home')
    context = {
        'objects': ['Эскалатор', '1 этаж электроника', 'Трубы на 4 этаже', 'Сантехника'],
        'executors': ['ТОО Рога и копыта', 'ИП Асылбеков', 'ИП Калиева', 'ОАО Казахтелеком'],
    }
    return render(request, 'site/ecopark/ecopark_create.html', context)
