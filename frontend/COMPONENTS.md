# metriX BPM — Components Library (FE-0.3)

Библиотека reusable Django-партиалов для построения экранов.
Все компоненты подключаются через `{% include %}` и принимают параметры через `with`.

---

## Файлы

```
backend/templates/site/components/
├── alert.html
├── badge_status.html
├── data_table.html
├── empty_state.html
├── filter_bar.html
├── form_field.html
├── modal.html
├── page_header.html
└── paginator.html             (обновлённый под Figma)

backend/static/site/css/
└── components.css             (скомпилированный из components.scss)

backend/apps/account/templatetags/
└── site_tags.py               (добавлены фильтры get_item, dict_get)
```

---

## 1. `page_header.html`

Заголовок страницы: хлебные крошки + название + кнопки действий.

### Параметры
| Имя | Тип | Описание |
|---|---|---|
| `title` | str | Заголовок (обязательно) |
| `subtitle` | str | Подзаголовок |
| `breadcrumbs` | list | `[{title, url}, ...]` — последняя без url |
| `back_url` | str | Если задан — рендерится стрелка назад |
| `actions` | str (HTML) | Блок с кнопками |
| `starred`, `editable`, `deletable` | bool | Иконки-действия |

### Пример
```django
{% include "site/components/page_header.html" with
   title="ТОО \"metriX Company\""
   breadcrumbs=breadcrumbs
   editable=True deletable=True %}
```

Где в view:
```python
breadcrumbs = [
    {'title': 'Контрагенты', 'url': '/companies/'},
    {'title': 'ТОО "metriX Company"'},
]
```

---

## 2. `data_table.html`

Таблица с пагинацией (на базе CustomPaginator) и сортировкой через query string.

### Параметры
| Имя | Тип | Описание |
|---|---|---|
| `columns` | list | `[{key, title, sortable, width}, ...]` |
| `rows` | list | queryset либо список словарей |
| `paginator` | CustomPaginator | из `project/paginator.py` |
| `sort_by`, `sort_order` | str | текущая сортировка |
| `empty_text` | str | текст если данных нет |
| `row_url` | str | шаблон URL для клика по строке |

### Пример
```django
{% include "site/components/data_table.html" with
   columns=table_columns rows=rows paginator=paginator
   sort_by=sort_by sort_order=sort_order %}
```

В view:
```python
columns = [
    {'key': 'name', 'title': 'ФИО', 'sortable': True},
    {'key': 'phone', 'title': 'Телефон', 'sortable': False},
    {'key': 'email', 'title': 'Email', 'sortable': True},
]
```

> Для не-словарей (queryset) используется фильтр `|get_item:col.key` который проверяет `dict.get`, `getattr`, индекс.

---

## 3. `filter_bar.html`

Панель фильтров (Период / ИП / Арендаторы / Статус оплаты / Применить).

### Параметры
| Имя | Тип | Описание |
|---|---|---|
| `filters` | list | список фильтров (см. ниже) |
| `submit_label` | str | текст кнопки (default "Применить") |
| `export_url` | str | URL "Экспорт в Excel" |

### Структура фильтра
```python
{
  'name': 'tenant',
  'label': 'Арендатор',
  'type': 'select2',           # select | select2 | date | daterange | text
  'options': [{'value': '1', 'label': 'ИП Рога'}, ...],
  'value': '',
  'placeholder': 'Все',
  'multiple': False,
}
```

### Пример
```django
{% include "site/components/filter_bar.html" with
   filters=filters export_url=export_url %}
```

> Select2 инициализируется автоматически на классе `.filter-bar__select2` если jQuery+Select2 подключены.

---

## 4. `form_field.html`

Универсальное поле формы. Два варианта использования:

### Вариант 1 — c Django form-объектом
```django
{% include "site/components/form_field.html" with field=form.email %}
```

### Вариант 2 — вручную
```django
{% include "site/components/form_field.html" with
   name="email" type="email" label="Email"
   value="" required=True placeholder="example@mail.kz" %}
```

### Поддерживаемые типы
`text, email, password, number, tel, url, date, time, datetime-local,`
`textarea, select, checkbox, radio, file, hidden`

### Параметры (для варианта 2)
| Имя | Описание |
|---|---|
| `name` | name атрибут |
| `type` | тип поля |
| `label` | подпись |
| `value` | значение |
| `placeholder` | placeholder |
| `required`, `disabled`, `readonly` | bool |
| `help_text` | подсказка |
| `error` | текст ошибки |
| `options` | список (для select/radio) |
| `select2` | bool — инициализировать select2 |
| `multiple` | bool |
| `min`, `max`, `step`, `maxlength`, `pattern` | для number/text |

---

## 5. `badge_status.html`

Статусный бейдж по ключу.

### Поддерживаемые статусы
| Ключ | Цвет | Текст |
|---|---|---|
| `paid` | green | Оплачено |
| `overdue` | red | Просрочено |
| `unpaid` | yellow | Не оплачено |
| `in_work` | blue | В работе |
| `done` | green | Завершена |
| `paused` | gray | Приостановлена |
| `open` | blue | Открыта |
| `rejected` | red | Отклонена |
| `pending` | yellow | На согласовании |
| `high`, `critical` | red | Высокий |
| `medium` | yellow | Средний |
| `low` | gray | Низкий |

### Параметры
| Имя | Описание |
|---|---|
| `status` | ключ статуса |
| `text` | переопределить текст |
| `icon` | Bootstrap icon name |
| `dot` | bool — точка слева |
| `size` | sm / md / lg |

### Пример
```django
{% include "site/components/badge_status.html" with status="paid" %}
{% include "site/components/badge_status.html" with status="overdue" dot=True %}
```

---

## 6. `modal.html`

Модальное окно на базе Bootstrap 5.

### Параметры
| Имя | Тип | Описание |
|---|---|---|
| `id` | str | id (обязательно) |
| `title` | str | заголовок |
| `size` | str | sm/md/lg/xl |
| `centered` | bool | по центру (default True) |
| `scrollable` | bool | скроллируемый body |
| `body` | HTML | разметка тела |
| `footer` | HTML | кастомный футер |
| `submit_label`, `cancel_label` | str | тексты кнопок |
| `submit_class` | str | CSS класс кнопки submit |
| `form_action`, `form_method` | str | оборачивает в form |
| `hide_footer` | bool | скрыть футер |

### Пример
```django
<button data-bs-toggle="modal" data-bs-target="#modalNew">Открыть</button>

{% include "site/components/modal.html" with
   id="modalNew" title="Новый контрагент"
   form_action=form_url submit_label="Сохранить" %}
```

---

## 7. `empty_state.html`

Пустое состояние "Данных нет".

### Параметры
| Имя | Описание |
|---|---|
| `icon` | Bootstrap icon (default `inbox`) |
| `title` | заголовок |
| `text` | описание |
| `action_url`, `action_label` | кнопка действия |
| `size` | sm/md/lg |

### Пример
```django
{% include "site/components/empty_state.html" with
   icon="people" title="Нет арендаторов"
   text="Добавьте первого арендатора"
   action_url="/tenants/new/" action_label="Добавить" %}
```

---

## 8. `alert.html`

Информационное сообщение.

### Параметры
| Имя | Описание |
|---|---|
| `type` | success / danger / warning / info |
| `title` | заголовок |
| `text` | текст |
| `icon` | переопределить иконку |
| `dismissible` | bool — можно закрыть |

### Пример
```django
{% include "site/components/alert.html" with
   type="success" text="Изменения сохранены" dismissible=True %}

{% include "site/components/alert.html" with
   type="warning" title="Внимание"
   text="Касса работает в автономном режиме" %}
```

---

## 9. `paginator.html` (обновлён)

Используется через template tag из `site_tags.py`:
```django
{% load site_tags %}
{% show_paginator paginator %}
```

Для AJAX-обработчика:
```django
{% show_paginator paginator True %}
```

---

## Установка

1. **Скопируй HTML-файлы** в `backend/templates/site/components/`
2. **Скопируй SCSS** в `backend/static/site/css/components.scss` и **скомпилируй**:
   ```bash
   sass backend/static/site/css/components.scss backend/static/site/css/components.css
   ```
3. **Добавь template-теги** в `backend/apps/account/templatetags/site_tags.py`:
   ```python
   @register.filter(name='get_item')
   def get_item(obj, key):
       if obj is None: return ''
       if isinstance(obj, dict): return obj.get(key, '')
       if hasattr(obj, str(key)): return getattr(obj, str(key))
       try: return obj[key]
       except: return ''
   ```
4. **Подключи `components.css`** в `base.html` (после `layout.css`):
   ```html
   <link rel="stylesheet" href="{% static 'site/css/components.css' %}">
   ```
5. **Перезапусти Docker:**
   ```bash
   docker compose exec web python manage.py collectstatic --noinput
   docker compose restart web
   ```

---

## Пример сборки экрана из компонентов

```django
{% extends "site/base.html" %}
{% load site_tags %}

{% block content %}
  {# Page header #}
  {% include "site/components/page_header.html" with
     title="Контрагенты"
     breadcrumbs=breadcrumbs %}

  {# Alert (если есть) #}
  {% if just_saved %}
    {% include "site/components/alert.html" with
       type="success" text="Сохранено" dismissible=True %}
  {% endif %}

  {# Filter bar #}
  {% include "site/components/filter_bar.html" with
     filters=filters export_url=export_url %}

  {# Data table #}
  {% include "site/components/data_table.html" with
     columns=columns rows=rows paginator=paginator %}

  {# Modal — добавить контрагента #}
  {% include "site/components/modal.html" with
     id="modalAdd" title="Новый контрагент"
     form_action=add_url %}
{% endblock %}
```