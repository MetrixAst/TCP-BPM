const STORAGE_KEY = 'quick_message_templates_v1'

export interface QuickMessageTemplate {
  id: string
  title: string
  /** Поддерживает {counterparty_name} — единственный плейсхолдер, который
   * можно подставить на клиенте без похода в 1С/бэкенд. */
  body: string
}

export const DEFAULT_QUICK_MESSAGE_TEMPLATES: QuickMessageTemplate[] = [
  {
    id: 'payment-reminder',
    title: 'Напоминание об оплате',
    body:
      'Добрый день, {counterparty_name}!\n\nНапоминаем об оплате по вашему договору. Если счёт уже оплачен — извините за напоминание.\n\nС уважением!',
  },
  {
    id: 'requisites-update',
    title: 'Уточнить реквизиты',
    body:
      'Добрый день, {counterparty_name}!\n\nПросим уточнить актуальные реквизиты для оплаты (email/контактный номер), чтобы мы могли направить вам счета без задержек.\n\nС уважением!',
  },
  {
    id: 'general-announcement',
    title: 'Общее объявление',
    body: 'Добрый день, {counterparty_name}!\n\n[Текст объявления]\n\nС уважением!',
  },
]

function readStoredTemplates(): QuickMessageTemplate[] | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return null
    return parsed.filter(
      (t): t is QuickMessageTemplate =>
        t && typeof t.id === 'string' && typeof t.title === 'string' && typeof t.body === 'string',
    )
  } catch {
    return null
  }
}

export function getQuickMessageTemplates(): QuickMessageTemplate[] {
  return readStoredTemplates() || DEFAULT_QUICK_MESSAGE_TEMPLATES
}

export function saveQuickMessageTemplates(templates: QuickMessageTemplate[]) {
  if (typeof window === 'undefined') return
  localStorage.setItem(STORAGE_KEY, JSON.stringify(templates))
}

export function resetQuickMessageTemplates() {
  if (typeof window === 'undefined') return
  localStorage.removeItem(STORAGE_KEY)
}

export function renderQuickMessageTemplate(template: QuickMessageTemplate, counterpartyName: string): string {
  return template.body.replace(/\{counterparty_name\}/g, counterpartyName)
}
