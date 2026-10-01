import type { Counterparty } from './api'

// Держим синхронно с бэкендом (app/services/invoice_service_type.py) — 5
// 1С-категорий подтверждены на реальных данных (ИП Ибрагимов, CityMall,
// счета от 2026-08-20): "Размещение вывески" и "АССП. Возмещение затрат
// услуги АССП." (реальное написание — два "С", не "АСПП"). "debt"/"other" —
// не из 1С-строк счёта (resolveInvoiceServiceTypes ниже их никогда не
// вернёт), а из xlsx-импорта (см. backend-докстринг того же файла) —
// добавлены сюда только чтобы значение service_type с сервера типизировалось
// корректно везде, где оно отображается как есть.
export type InvoiceServiceType =
  | 'rent'
  | 'utilities'
  | 'operations'
  | 'signage'
  | 'assp'
  | 'debt'
  | 'other'

export function extractPhoneOptions(counterparty: Counterparty, extraPhones: string[] = []): string[] {
  const raw = [counterparty.phoneNumber || '', counterparty.phone || '', ...extraPhones]
    .filter(Boolean)
    .join(';')
  const chunks = raw
    .split(/[;,/\n]/g)
    .map((p) => p.trim())
    .filter(Boolean)
  const unique: string[] = []
  for (const phone of chunks) {
    if (!unique.includes(phone)) unique.push(phone)
  }
  return unique
}

const RENT_KEYWORDS = ['аренд']
const UTIL_KEYWORDS = ['коммун', 'электр', 'вода', 'тепл', 'тбо', 'мусор', 'канал', 'интернет']
const OPS_KEYWORDS = ['эксплуат', 'маркетинг']
const SIGNAGE_KEYWORDS = ['вывеск']
const ASSP_KEYWORDS = ['ассп']

// Порядок, в котором типы показываются в одном счёте — совпадает с
// SERVICE_TYPE_ORDER на бэкенде.
const SERVICE_TYPE_ORDER: InvoiceServiceType[] = ['rent', 'utilities', 'operations', 'signage', 'assp']

function lineMatches(name: string, keywords: string[]): boolean {
  const n = name.toLowerCase()
  return keywords.some((kw) => n.includes(kw))
}

export function resolveInvoiceServiceTypes(invoice: {
  items?: Array<{ name?: string }>
}): InvoiceServiceType[] {
  const found = new Set<InvoiceServiceType>()
  for (const item of invoice.items || []) {
    const name = item.name || ''
    if (lineMatches(name, RENT_KEYWORDS)) found.add('rent')
    if (lineMatches(name, UTIL_KEYWORDS)) found.add('utilities')
    if (lineMatches(name, OPS_KEYWORDS)) found.add('operations')
    if (lineMatches(name, SIGNAGE_KEYWORDS)) found.add('signage')
    if (lineMatches(name, ASSP_KEYWORDS)) found.add('assp')
  }
  return SERVICE_TYPE_ORDER.filter((t) => found.has(t))
}

export function resolveInvoiceServiceType(invoice: {
  items?: Array<{ name?: string }>
}): InvoiceServiceType | 'unknown' {
  const types = resolveInvoiceServiceTypes(invoice)
  if (types.length === 0) return 'unknown'
  return types[0]
}

export const SERVICE_TYPE_LABELS: Record<InvoiceServiceType, string> = {
  rent: 'Аренда',
  utilities: 'Коммунальные услуги',
  operations: 'Маркетинг',
  signage: 'Вывеска',
  assp: 'АССП',
  debt: 'Долг пред. периода',
  other: 'Прочее',
}

/** "rent,utilities" (как хранится в TenantPayment.service_type) -> "Аренда, Ком.услуги". */
export function formatServiceTypeLabel(raw: string | null | undefined): string {
  if (!raw || raw === 'unknown') return '—'
  return raw
    .split(',')
    .map((t) => SERVICE_TYPE_LABELS[t.trim() as InvoiceServiceType] || t.trim())
    .join(', ')
}
