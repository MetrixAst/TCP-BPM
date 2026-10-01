import type { Counterparty, Notification } from './api'

export function isNotificationGatewayTimeout(error: unknown): boolean {
  const err = error as { response?: { status?: number } }
  return err.response?.status === 504
}

// reportTypeLabel — undefined когда тип услуги не был явно выбран
// пользователем (см. обсуждение 2026-09-18: раньше UI молча предвыбирал
// "Аренда" по умолчанию, из-за чего в бэкенд уходил service_type=rent,
// даже если отправлялся счёт другого типа). Пусто — просто не пишем
// скобки, а не показываем их пустыми "()".
function typeSuffix(reportTypeLabel?: string): string {
  return reportTypeLabel ? ` (${reportTypeLabel})` : ''
}

export function notificationSendDeferredMessage(reportTypeLabel?: string): string {
  return `Отправка запущена${typeSuffix(reportTypeLabel)}. Сообщение и PDF придут в WhatsApp в течение 1–2 минут.`
}

export function notificationSendResultMessage(
  notification: Notification,
  reportTypeLabel?: string,
): string {
  const suffix = typeSuffix(reportTypeLabel)
  const status = notification.status
  if (status === 'delivered' || status === 'read') {
    return `Сообщение отправлено в WhatsApp${suffix}`
  }
  if (notification.whatsapp_sent) {
    return `Сообщение отправлено в WhatsApp${suffix}`
  }
  if (notification.queued) {
    return `Сообщение поставлено в очередь${suffix}. PDF и WhatsApp отправятся в фоне — обычно в течение 1–2 минут.`
  }
  if (notification.whatsapp_sent === false || status === 'sent') {
    return `Не удалось отправить в WhatsApp${suffix}. Проверьте Green API, номер телефона и логи backend.`
  }
  return `Уведомление создано${suffix}`
}

export function notificationTypeForCounterparty(cp: Counterparty): string {
  const status = cp.latestInvoice?.paymentStatus?.toLowerCase()
  if (status === 'overdue') return 'overdue'
  if (status === 'paid') return 'same_day'
  if (status === 'unpaid') return 'three_days'
  return 'overdue'
}

// Real bug found 2026-09-02: NotificationPopover's "Отправить" button sent
// notification_type derived from notificationTypeForCounterparty(counterparty)
// — the counterparty's globally-cached "latest invoice" status — instead of
// the status of the actual invoice ROW the user clicked. A row whose own due
// date hadn't passed yet still said "ВНИМАНИЕ: платёж просрочен" whenever
// that counterparty's latest-tracked invoice elsewhere happened to be
// overdue/partial/stale. The popover already computes the right per-row
// status correctly for its own button LABEL (paymentStatus ?? payment?.status
// ?? counterparty?.latestInvoice?.paymentStatus) — this mirrors the backend's
// own bulk_debtor_notify_service._notification_type_for_status mapping so a
// manual single send and the bulk mailing agree on the same row's status.
export function notificationTypeForStatus(status?: string | null): string {
  const s = status?.toLowerCase()
  if (s === 'overdue') return 'overdue'
  if (s === 'unpaid') return 'three_days'
  return 'same_day'
}

// axios responseType:'blob' wraps even error bodies as a Blob, so the plain-text
// detail the backend sends (e.g. download failures) never reaches response.data.detail —
// read it off the blob first, then fall back to the normal JSON-shaped formatting.
export async function formatBlobApiError(error: unknown): Promise<string> {
  const err = error as { response?: { data?: unknown } }
  const data = err.response?.data
  if (data instanceof Blob && data.type.includes('text')) {
    const text = (await data.text()).trim()
    if (text) return text
  }
  return formatApiError(error)
}

export function formatApiError(error: unknown): string {
  const err = error as {
    message?: string
    code?: string
    config?: { baseURL?: string; url?: string }
    response?: { status?: number; data?: { detail?: unknown } }
  }
  const detail = err.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d: { msg?: string }) => d.msg)
      .filter(Boolean)
      .join('; ')
  }
  if (err.response?.status) {
    return `Ошибка сервера (${err.response.status})`
  }
  if (err.code === 'ERR_NETWORK' || err.message === 'Network Error') {
    const base = err.config?.baseURL || ''
    const path = err.config?.url || ''
    const target = base ? `${base}${path}` : 'API'
    const crossOrigin =
      typeof window !== 'undefined' &&
      target.includes('api.invoice.') &&
      !target.includes('/api-proxy')
    const proxyHint = crossOrigin
      ? ' '
      : ''
    const chromeHint =
      typeof window !== 'undefined' &&
      /Chrome/i.test(navigator.userAgent) &&
      !/Edg/i.test(navigator.userAgent)
        ? ' В Chrome часто мешают расширения — попробуйте инкогнито.'
        : ''
    const timeoutHint =
      err.response?.status === 504 || String(target).includes('504')
        ? ' Сервер не успел ответить (504) — часто из‑за 1С или перегрузки API.'
        : ''
    return `Нет связи с сервером (${target}).${timeoutHint}${proxyHint}${chromeHint}`
  }
  return err.message || 'Неизвестная ошибка'
}
