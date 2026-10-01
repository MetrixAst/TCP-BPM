# Настройка i18n

## Установка зависимостей

```bash
cd frontend
npm install next-intl
```

## Структура локализации

- `messages/ru.json` - Русский язык
- `messages/kz.json` - Казахский язык  
- `messages/en.json` - Английский язык

## Использование

### В компонентах

```tsx
import { useTranslations } from 'next-intl'

export default function MyComponent() {
  const t = useTranslations('header')
  
  return <h1>{t('title')}</h1>
}
```

### Переключение языка

Язык переключается через URL:
- `/ru` - Русский
- `/kz` - Казахский
- `/en` - Английский

По умолчанию при заходе на `/` происходит редирект на `/ru`.

## Добавление новых переводов

1. Добавьте ключ в `messages/ru.json`
2. Добавьте перевод в `messages/kz.json` и `messages/en.json`
3. Используйте через `useTranslations('namespace')`
