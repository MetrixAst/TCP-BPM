# Инструкция для разработчиков TRC BPM

## Первоначальная настройка

### 1. Клонирование репозитория

```bash
git clone https://github.com/MetrixAst/TCP-BPM.git
cd TCP-BPM
```

### 2. Переключение на ветку develop

```bash
git checkout develop
git pull origin develop
```

> **Важно:** Никогда не работайте напрямую в `main` или `develop`. Всегда создавайте feature-ветку.

---

## Git Workflow

```
main                ← продакшн (защищена, только через PR из develop)
  └── develop       ← интеграционная ветка (защищена, только через PR из feature/*)
        └── feature/*   ← ваши рабочие ветки
```

---

## Ежедневный процесс работы

### Шаг 1: Перед началом работы — обновить develop

```bash
git checkout develop
git pull origin develop
```

### Шаг 2: Создать feature-ветку от develop

Формат имени ветки: `feature/<task-id>-<краткое-описание>`

```bash
# Примеры:
git checkout -b feature/task-1.1-update-statuses develop
git checkout -b feature/task-2.1-company-model develop
```

### Шаг 3: Работать и коммитить

```bash
# Внесли изменения...
git add .
git status                    # проверить что добавляется
git commit -m "Update task statuses in enums.py"
```

Правила коммитов:
- Один коммит = одно логическое изменение
- Сообщение на английском, начинается с глагола: `Add`, `Update`, `Fix`, `Remove`, `Refactor`
- Примеры:
  - `Add priority field to Task model`
  - `Update task status enum values`
  - `Fix workflow permission check for co-executors`
  - `Add data migration for old task statuses`

### Шаг 4: Запушить ветку

```bash
git push -u origin feature/task-1.1-update-statuses
```

### Шаг 5: Создать Pull Request

1. Открыть GitHub → репозиторий → вкладка "Pull Requests"
2. Нажать **"New Pull Request"**
3. Base: `develop` ← Compare: `feature/task-1.1-update-statuses`
4. Заполнить описание PR:

```markdown
## Что сделано
- Заменены статусы задач: TO_DO/DOING/DONE/ARCHIVE → CREATED/ACCEPTED/REJECTED/REVISION/COMPLETED
- Обновлены методы get_full(), get_actions(), get_notification_text()

## Связанная задача
TASK-1.1

## Как тестировать
1. Запустить миграции
2. Открыть список задач — проверить новые статусы
3. Создать задачу — проверить что статус CREATED
```

5. Назначить ревьюера (руководитель проекта)
6. Дождаться approve → нажать **"Merge"**

### Шаг 6: После merge — обновить develop локально

```bash
git checkout develop
git pull origin develop
```

Старую feature-ветку можно удалить:

```bash
git branch -d feature/task-1.1-update-statuses
```

---

## Если нужно обновить feature-ветку свежим develop

Бывает, что пока вы работаете, в `develop` влили другие PR. Чтобы получить эти изменения:

```bash
git checkout develop
git pull origin develop
git checkout feature/task-1.1-update-statuses
git merge develop
```

Если возник конфликт:
1. Открыть файлы с конфликтами (помечены `<<<<<<<`)
2. Разрешить конфликт вручную
3. `git add .` → `git commit` → `git push`

---

## Что НЕЛЬЗЯ делать

- **Пушить напрямую в `main`** — только через PR из `develop`
- **Пушить напрямую в `develop`** — только через PR из `feature/*`
- **`git push --force`** — никогда без согласования
- **Коммитить `.env`, пароли, ключи** — они в `.gitignore`
- **Большие коммиты** — лучше несколько маленьких, чем один огромный

---

## Структура веток по задачам

### Работник A (Модуль задач)

| Задача | Ветка |
|---|---|
| TASK-1.1 | `feature/task-1.1-update-statuses` |
| TASK-1.2 | `feature/task-1.2-priority` |
| TASK-1.3 | `feature/task-1.3-co-executors` |
| TASK-1.4 | `feature/task-1.4-workflow` |
| TASK-1.5 | `feature/task-1.5-templates` |
| TASK-1.6 | `feature/task-1.6-data-migrations` |
| TASK-1.7 | `feature/task-1.7-views-update` |

### Работник B (HR модуль)

| Задача | Ветка |
|---|---|
| TASK-2.1 | `feature/task-2.1-company-model` |
| TASK-2.2 | `feature/task-2.2-position-model` |
| TASK-2.3 | `feature/task-2.3-employee-extend` |
| TASK-2.4 | `feature/task-2.4-migrate-positions` |
| TASK-2.5 | `feature/task-2.5-employee-forms` |
| TASK-2.6 | `feature/task-2.6-employee-views` |
| TASK-2.7 | `feature/task-2.7-orgchart` |
| TASK-2.8 | `feature/task-2.8-hr-menu` |

---

## Запуск проекта локально

### Через Docker

```bash
docker-compose up --build
```

Сервисы:
- Web: http://localhost:80
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### Без Docker (для разработки)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # заполнить переменные
python manage.py migrate
python manage.py runserver
```

---

## Порядок merge при зависимых задачах

Некоторые задачи зависят друг от друга. Порядок merge в `develop`:

**Работник A:**
1. TASK-1.1 (статусы) — первый
2. TASK-1.2 (priority) + TASK-1.3 (co_executors) — параллельно после 1.1
3. TASK-1.4 (workflow) — после 1.1 + 1.3
4. TASK-1.6 (миграции) — после 1.1 + 1.2 + 1.3
5. TASK-1.5 (шаблоны) + TASK-1.7 (views) — после всех

**Работник B:**
1. TASK-2.1 (Company) — первый
2. TASK-2.2 (Position) — после 2.1
3. TASK-2.3 (Employee) — после 2.2
4. TASK-2.4 (миграция) — после 2.2 + 2.3
5. TASK-2.5 (формы) + TASK-2.6 (views) — после 2.3
6. TASK-2.7 (OrgChart) + TASK-2.8 (меню) — последние

---

## Контакты

По вопросам git и workflow → руководитель проекта.
