# TRC BPM — Статус спринтов

**Актуальная ветка:** `sprint`  
**Обновлено:** 21.05.2026  
**Merge в `develop`:** ⏸ **не делаем пока** (по решению команды)

---

## Прогресс проекта

| Фаза | Статус |
|------|--------|
| Phase 1 — Задачи | ✅ ~90% |
| Phase 2 — HR | ✅ ~95% |
| Phase 3 — Enbek.kz | ⏸ заморожена (нет API) |
| Phase 4 — 1С | ✅ 100% |
| Phase 5 — Финансы Core | ✅ 100% |
| Phase 6 — Дашборды | ✅ 100% |
| Phase 7 — Финализация | ✅ 100% (код в `sprint`) |
| **ИТОГО по плану** | **~100%** |

---

## Спринт 1 — Phase 5 остаток ✅

| Задача | PR | Статус |
|--------|-----|--------|
| BE-2.fix companies/positions | #67 | ✅ |
| BE-2.21 Celery hr_check_expirations | #68 | ✅ |
| BE-5.13 ExchangeRate + НБ РК | #69 | ✅ |
| BE-5.14 Отправка счетов email | #71 | ✅ |
| FE-5.4 Бюджет шаблоны | #72 | ✅ |
| FE-5.5 ОПиУ + ДДС + кредитка | #73 | ✅ |
| COLLAB-3 Финансы Core | #74 | ✅ |

---

## Спринт 2 — Phase 6 BE ✅

| Задача | PR | Статус |
|--------|-----|--------|
| BE-6.1 Executive Dashboard backend | #76 | ✅ |
| BE-6.4 Аналитика аренды | #75 | ✅ |
| BE-6.2 CF chart endpoints | #77 | ✅ |
| BE-6.3 Drill-down до 1С | #78 | ✅ |
| BE-6.5 Forecast CF | #79 | ✅ |
| BE-6.6 Scenarios API | #80 | ✅ |
| BE-6.7 Excel export | #81 | ✅ |
| BE-6.8 Global finance filters | #82 | ✅ |
| BE-6.9 Multi-currency | #83 | ✅ |

---

## Спринт 3 — Phase 6 FE ✅

| Задача | PR | Статус |
|--------|-----|--------|
| FE-6.1 Executive Dashboard | #84 | ✅ |
| FE-6.3 Аналитика аренды | #85 | ✅ |
| FE-6.5 Глобальные фильтры | #87 | ✅ |
| FE-6.4 Прогноз CF + Сценарии | #86 | ✅ |
| FE-6.2 Multi-currency toggle | #88 | ✅ |
| COLLAB-4 Стыковка дашбордов | #89 | ✅ |

---

## Спринт 4 — Phase 7 + COLLAB ✅

### Phase 7 BE

| Задача | PR | Статус | Результат |
|--------|-----|--------|-----------|
| BE-7.1 REST API `/api/v1/` | #90 | ✅ | tasks, hr, finances ViewSets |
| BE-7.2 JWT | #91 | ✅ | `/api/token/`, `/api/token/refresh/` |
| BE-7.3 Swagger / OpenAPI | #92 | ✅ | `/api/docs/`, `/api/schema/` |
| BE-7.7 Audit trail | #93 | ✅ | `apps/audit/`, `/audit/log/` |
| BE-7.4 pytest coverage ≥70% | #94 | ✅ | pytest + cov |
| BE-7.5 Docker prod | #95 | ✅ | `docker-compose.prod.yml`, nginx |
| BE-7.6 CI/CD | #96 | ✅ | `.github/workflows/ci.yml` |

### COLLAB (стыковка + UAT)

| Задача | PR | Статус | Что сделано |
|--------|-----|--------|-------------|
| **COLLAB-1** HR | #97 | ✅ | Smoke HR (admin/staff); цепочка документ → допуск → сертификация → отпуск + Excel; **fix:** superuser получает `role` (без этого HR 403) |
| **COLLAB-2** 1С | #98 | ✅ | List/detail контрагентов, Select2 API, счёт с позициями; sync при недоступной 1С без падения |
| **COLLAB-5** UAT | #99 | ✅ | `tests_uat.py`: JWT, `/api/v1/`, Swagger, audit (admin/staff), docker-compose.prod.yml, CI |

**Merge в `sprint`:** #97 → #98 → #99 (все влиты, HEAD: `9b4f987`)

---

## Что осталось (без merge в develop)

### 1. Ручной UAT на staging (COLLAB-5, часть 2)

Автотесты в #99 — готовы. **Ручные сценарии** — после поднятия prod compose:

```bash
git checkout sprint
git pull origin sprint

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

| Роль | Сценарий |
|------|----------|
| HR | Сотрудник → документ → допуск → сертификация → отпуск → checkin |
| Бухгалтер | Реестр → счёт → email → оплачен |
| CFO | Dashboard → drill-down → бюджет → сценарии → прогноз |
| Owner | Executive dashboard → аренда → Excel |
| Admin | Audit log, все модули |

**Критерии:** нет 500, права 403 где нужно, JWT и Swagger отвечают.

### 2. Merge `sprint` → `develop` — ⏸ отложен

Когда будете готовы:

```bash
git checkout develop
git pull origin develop
git merge sprint
# разрешить конфликты если есть
git push origin develop
```

Пока **не мержим** — вся готовая работа живёт в `sprint`.

### 3. Backlog UI/UX (опционально, не блокирует 100%)

| # | Правка | Приоритет |
|---|--------|-----------|
| 1 | Favicon MetriX | Быстро |
| 2 | Логотип: X зелёная | Быстро |
| 3 | Единая дизайн-система | Средне |
| 4 | Меню задач — убрать «я» | Быстро |
| 5–7 | HR-календарь | Средне |
| 8–9 | Контрагенты + реестр — стили | Средне |
| 10 | Сотрудник → оргструктура | Средне |
| 11 | Кнопка «Удалить» сотрудника | Средне |

### 4. Phase 3 — Enbek.kz

Заморожена до появления API. Поля `external_enbek_id` в моделях зарезервированы.

---

## Инфраструктура (после Sprint 4)

| Компонент | Где |
|-----------|-----|
| REST API | `/api/v1/` |
| JWT | `/api/token/`, `/api/token/refresh/` |
| Swagger | `/api/docs/` |
| Audit | `/audit/log/` (Administrator) |
| CI | `.github/workflows/ci.yml` |
| Prod Docker | `docker-compose.yml` + `docker-compose.prod.yml` |
| Тесты | `pytest` в `backend/`, coverage ≥70% |

---

## Для нового агента

**Сейчас не нужен большой спринт разработки.** Возможные задачи:

1. Помочь с **ручным UAT** на staging и завести баги
2. Закрыть **backlog UI/UX** (отдельные ветки от `sprint`)
3. Подготовить **merge sprint → develop** (только по запросу)
4. **Enbek** — когда появится API

Промпт:

> *Ветка `sprint`. Phase 7 и COLLAB-1/2/5 закрыты (#90–#99). Merge в develop не делать. Нужно: [UAT / UI backlog / подготовка merge].*

---

## История ветки `sprint`

```
develop (#66 и ранее)
  → Sprint 1 (#67–#74) Phase 5
  → Sprint 2 (#75–#83) Phase 6 BE
  → Sprint 3 (#84–#89) Phase 6 FE
  → Sprint 4 (#90–#99) Phase 7 + COLLAB
```

**Всего PR в sprint:** #67–#99 (кроме закрытых дублей)
