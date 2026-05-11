# metriX BPM — Design Tokens

Figma → CSS variable mapping для проекта **metriX BPM**.  
Технология: Bootstrap 5 + кастомная тема через переопределение SCSS-переменных и CSS custom properties (`:root`).

---

## Файлы

| Файл | Назначение |
|------|-----------|
| `backend/static/site/css/_tokens.scss` | Все дизайн-токены: цвета, шрифты, отступы, радиусы, тени |
| `backend/static/site/css/_components.scss` | Стили компонентов, построенные на токенах |
| `frontend/DESIGN-TOKENS.md` | Этот документ — маппинг Figma → CSS |

---

## Цвета (Colors)

### Primary

| Figma name | CSS Variable | Hex |
|-----------|-------------|-----|
| Primary / 600 | `--color-primary` | `#2563EB` |
| Primary / 700 (hover) | `--color-primary-hover` | `#1D4ED8` |
| Primary / 50 (light bg) | `--color-primary-light` | `#EFF6FF` |
| Primary / 500 | `--color-primary-500` | `#3B82F6` |

### Статусные цвета (Status)

| Figma / Компонент | CSS Variable | Hex | Применение |
|------------------|-------------|-----|-----------|
| Success / Green | `--color-success` | `#16A34A` | Badge «Оплачено», иконка ✓ |
| Success BG | `--color-success-bg` | `#DCFCE7` | Фон badge |
| Danger / Red | `--color-danger` | `#DC2626` | Badge «Просрочено», кнопка «Удалить» |
| Danger BG | `--color-danger-bg` | `#FEE2E2` | Фон badge |
| Warning / Orange | `--color-warning` | `#F59E0B` | Badge «Не оплачено», иконка ⊙ |
| Warning BG | `--color-warning-bg` | `#FEF3C7` | Фон badge |
| Info / Blue | `--color-info` | `#3B82F6` | Информационные элементы |

### Нейтральные / Gray

| Figma Neutral | CSS Variable | Hex |
|--------------|-------------|-----|
| Gray 50 | `--color-neutral-50` | `#F9FAFB` |
| Gray 100 | `--color-neutral-100` | `#F3F4F6` |
| Gray 200 | `--color-neutral-200` | `#E5E7EB` |
| Gray 400 | `--color-neutral-400` | `#9CA3AF` |
| Gray 500 | `--color-neutral-500` | `#6B7280` |
| Gray 700 | `--color-neutral-700` | `#374151` |
| Gray 800 | `--color-neutral-800` | `#1F2937` |

### Поверхности / Фоны

| Figma | CSS Variable | Hex | Применение |
|------|-------------|-----|-----------|
| Page BG | `--color-bg` | `#F5F7FA` | Фон страницы |
| Surface / White | `--color-surface` | `#FFFFFF` | Карточки, модалки, сайдбар |
| Border | `--color-border` | `#E5E7EB` | Все границы (в Figma — dashed) |

### Текст

| Figma | CSS Variable | Применение |
|------|-------------|-----------|
| Text Primary | `--color-text-primary` `#111827` | Основной текст |
| Text Secondary | `--color-text-secondary` `#6B7280` | Подписи, лейблы |
| Text Muted | `--color-text-muted` `#9CA3AF` | Placeholder, disabled |
| Text Link | `--color-text-link` `#2563EB` | Ссылки (nikanika.kz) |

---

## Типографика (Typography)

| Figma Style | CSS Variable | Значение | Применение |
|------------|-------------|---------|-----------|
| Heading / H1 | `--font-size-h1` | `2rem` (32px) | Большие числа (35, 25, 7, 3) |
| Heading / H3 | `--font-size-h3` | `1.25rem` (20px) | Заголовки секций (Контрагенты) |
| Heading / H4 | `--font-size-h4` | `1.125rem` (18px) | Название карточки (ТОО "metriX Company") |
| Body | `--font-size-body` | `0.875rem` (14px) | Текст таблиц, форм |
| Caption | `--font-size-caption` | `0.75rem` (12px) | Лейблы, метаданные, пагинация |
| — | `--font-family-base` | `'Inter', system-ui` | Единый шрифт |
| Regular | `--font-weight-regular` | `400` | — |
| Medium | `--font-weight-medium` | `500` | — |
| Semibold | `--font-weight-semibold` | `600` | Заголовки карточек |
| Bold | `--font-weight-bold` | `700` | H1-H2, числовые метрики |

---

## Отступы (Spacing Scale)

| Token | CSS Variable | px |
|------|-------------|-----|
| space-1 | `--space-1` | 4px |
| space-2 | `--space-2` | 8px |
| space-3 | `--space-3` | 12px |
| space-4 | `--space-4` | 16px |
| space-5 | `--space-5` | 20px |
| space-6 | `--space-6` | 24px |
| space-8 | `--space-8` | 32px |
| space-12 | `--space-12` | 48px |

> Из Figma: padding панелей = 20–24px, gap между элементами = 8–12px, внутренние отступы кнопок = 8×16px.

---

## Радиусы (Border Radius)

| Figma | CSS Variable | px | Применение |
|------|-------------|-----|-----------|
| Radius SM | `--radius-sm` | 4px | Inputs, мелкие элементы |
| Radius MD | `--radius-md` | 6px | Кнопки, badges |
| Radius LG | `--radius-lg` | 8px | Карточки, выпадашки |
| Radius 2XL | `--radius-2xl` | 20px | Основная карточка контента (Figma: `radius: 20`) |
| Radius Full | `--radius-full` | 9999px | Аватары, pill-badges, иконки статусов |

---

## Тени (Shadows)

| CSS Variable | Применение |
|-------------|-----------|
| `--shadow-sm` | Карточки по умолчанию |
| `--shadow-md` | Hover-состояния, приподнятые элементы |
| `--shadow-lg` | Выпадающие меню, dropdown |
| `--shadow-modal` | Модальные окна |

---

## Брейкпоинты (Breakpoints)

Используются Bootstrap 5 стандартные:

| Name | px |
|------|----|
| sm | 576px |
| md | 768px |
| lg | 992px |
| xl | 1200px |
| xxl | 1400px |

---

## Компоненты (Component Catalog)

### `btn` — Кнопки

| Вариант класса | Figma | Применение |
|---------------|------|-----------|
| `.btn--primary` | Синяя заливка | «Применить», «Сохранить», «Добавить» |
| `.btn--secondary` | Белая с рамкой | «Экспортировать Excel» |
| `.btn--danger` | Красная | Деструктивные действия |
| `.btn--outline-danger` | Красная рамка | «Удалить» в таблице |
| `.btn--ghost` | Без фона | «Редактировать» в таблице |
| `.btn--sm` | Маленькая | В таблицах и тулбарах |
| `.btn--icon` | Иконка без текста | Тулбарные иконки |

---

### `badge` — Статусные метки

| Класс | Figma label | Цвет |
|-------|------------|------|
| `.badge--success` | Оплачено | Зелёный |
| `.badge--danger` | Просрочено | Красный |
| `.badge--warning` | Не оплачено | Оранжевый |
| `.badge--primary` | В работе | Синий |
| `.badge--high` | Высокий (приоритет) | Красный |
| `.badge--medium` | Средний | Оранжевый |
| `.badge--low` | Низкий | Серый |
| `.badge--done` | Завершена | Зелёный |
| `.badge--paused` | Приостановлена | Серый |

---

### `card` — Карточки

- `.card` — базовая карточка (radius: 20px, border, shadow-sm)  
- `.stat-card` — карточка с метрикой (Оплачено: 25, Не оплачено: 7, Просрочено: 3)

---

### `table` — Таблица

- `.table-wrapper` — обёртка с dashed-рамкой (из Figma)  
- `.table` — базовая таблица со строками hover-состояния  
- Колонки: ИП, Арендатор, Уведомления, Дата, Крайний срок, Статус оплаты, Дата оплаты, Действия

---

### `form` — Формы

- `.form-control` — текстовое поле  
- `.form-select` — дропдаун (стрелка через SVG background)  
- `.btn-toggle-group` — переключатель вариантов (Юридическое / Физическое лицо, Резидент / Нерезидент, Мужской / Женский)

---

### `modal` — Модальные окна

Figma: «Новый контрагент» — grid 2 колонки, заголовок + кнопка ×, footer с «Сохранить».

---

### `alert` — Системные сообщения

`.alert--success / --danger / --warning / --info`

---

### `breadcrumb` — Хлебные крошки

Figma: `Контрагенты / ТОО "metriX Company"` — разделитель `/`, последний элемент жирный.

---

### `pagination` — Пагинация

Figma: `‹ 1 2 3 ••• 97 98 99 ›` — активная страница на синем фоне.

---

### `tabs` — Вкладки

Figma: `Заявки (1) + | Задачи (12) + | Счета (3) + | Процессы +`  
Активная вкладка — синяя нижняя линия + синий текст. Счётчик — синяя pill.

---

### `sidebar` — Навигационная панель

Ширина: 260px. Элементы: логотип, nav-items с иконками, sub-items (Финансы → Реестр оплат, Финансовый календарь...), footer с аватаром пользователя.

Figma nav items: Менеджер задач, Документооборот, Компании, Закупки, Финансы, HR, Эксплуатация, Заявки от арендаторов, Показатели.

---

### `topbar` — Шапка

Содержит (слева→направо):
1. Поиск (поле с иконкой)
2. Переключатель объекта: «Ритц-Палас ▾»
3. Временная зона: «Алматы GMT +5 ▾»
4. Языковой переключатель: `🌐 Рус | Каз | Eng`
5. Кнопка выхода `[→`

---

## Используемые токены по Bootstrap 5 override

```scss
// В вашем bootstrap-custom.scss до @import "bootstrap":
@import 'tokens';

$primary:          #2563EB;
$success:          #16A34A;
$danger:           #DC2626;
$warning:          #F59E0B;
$info:             #3B82F6;
$font-family-base: 'Inter', system-ui, sans-serif;
$font-size-base:   0.875rem;
$border-radius:    6px;
$border-radius-lg: 8px;
$box-shadow:       0 4px 6px -1px rgba(0,0,0,.08);

@import "~bootstrap/scss/bootstrap";
@import 'tokens';
@import 'components';
```