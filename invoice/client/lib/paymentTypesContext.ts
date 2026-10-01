import type { InvoiceServiceType } from './counterpartyPhoneUtils'

export type PaymentTypesEnabled = Record<InvoiceServiceType, boolean>

export const DEFAULT_PAYMENT_TYPES_ENABLED: PaymentTypesEnabled = {
  rent: true,
  utilities: true,
  operations: true,
  // Нет per-tenant вкл/выкл для вывески/АССП/долга/прочего (осознанное
  // решение — см. invoice_service_type.py docstring), всегда включены на
  // этом уровне. Показывать ли их в конкретном фильтре, если данных 0 в
  // текущем периоде — отдельный вопрос, см. serviceTypeOptions в
  // InvoiceRegistryTable.tsx (динамическая часть, не эта статическая).
  signage: true,
  assp: true,
  debt: true,
  other: true,
}

let current: PaymentTypesEnabled = { ...DEFAULT_PAYMENT_TYPES_ENABLED }

export function setPaymentTypesEnabled(value?: Partial<PaymentTypesEnabled> | null) {
  current = {
    ...DEFAULT_PAYMENT_TYPES_ENABLED,
    ...(value || {}),
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('paymentTypesChanged'))
  }
}

export function getPaymentTypesEnabled(): PaymentTypesEnabled {
  return current
}

export function isPaymentTypeEnabled(type: InvoiceServiceType): boolean {
  return current[type] ?? true
}

export function enabledPaymentTypes(): InvoiceServiceType[] {
  return (
    ['rent', 'utilities', 'operations', 'signage', 'assp', 'debt', 'other'] as InvoiceServiceType[]
  ).filter(isPaymentTypeEnabled)
}

// Типы, которые всегда стоит показывать в фильтре, даже с 0 счетов за период
// — это основные категории тенанта, скрыть их выглядело бы как баг ("куда
// делась аренда?"). Остальные enabled-типы (вывеска/АССП/долг/прочее) —
// длинный хвост, актуальный не для каждого ТЦ/периода: показываем только
// когда PaymentAnalytics.service_types_present говорит, что за них правда
// есть хотя бы один счёт в текущем периоде (см. InvoiceRegistryTable.tsx).
export const ALWAYS_VISIBLE_PAYMENT_TYPES: InvoiceServiceType[] = ['rent', 'utilities', 'operations']

export function firstEnabledPaymentType(
  preferred: InvoiceServiceType = 'rent',
): InvoiceServiceType {
  if (isPaymentTypeEnabled(preferred)) return preferred
  return enabledPaymentTypes()[0] || 'rent'
}
