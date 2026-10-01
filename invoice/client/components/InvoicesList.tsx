'use client'

import { useState, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { paymentApi } from '@/lib/api'
import { getEffectiveTenantId } from '@/lib/tenantContext'
import { useOneCDataLoad } from '@/lib/useOneCDataLoad'
import { formatApiError, formatBlobApiError } from '@/lib/notificationHelpers'
import { useToast } from '@/lib/toastContext'
import { resolveInvoiceServiceTypes, SERVICE_TYPE_LABELS } from '@/lib/counterpartyPhoneUtils'
import TabRefreshButton from './TabRefreshButton'

interface InvoiceItem {
  name: string
  quantity: number
  price: number
  amount: number
}

interface Counterparty {
  id: string
  name: string
  bin: string
}

interface Invoice {
  id: string
  number: string
  date: string
  counterparty_name?: string
  counterparty_id?: string
  counterparty?: Counterparty
  amount: number
  vat?: number
  currency: string
  status: string
  paid_amount?: number
  pdf?: string
  pdf_downloaded?: boolean
  pdf_file_path?: string
  items: InvoiceItem[]
  /** 'xlsx' — синтетический id (не реальный 1С-счёт), скачивается через
   * отдельный backend-эндпоинт, см. handleDownloadPdf. */
  source: string
}

function normalizeInvoice(raw: Record<string, unknown>): Invoice {
  const cp = raw.counterparty as Counterparty | undefined
  const counterpartyName =
    (raw.counterparty_name as string) ||
    cp?.name ||
    ''
  const counterpartyId = (raw.counterparty_id as string) || cp?.id || ''
  const counterpartyBin = cp?.bin || ''
  return {
    id: String(raw.id || ''),
    number: String(raw.number || ''),
    date: String(raw.date || ''),
    counterparty_name: counterpartyName,
    counterparty_id: counterpartyId,
    counterparty: {
      id: counterpartyId,
      name: counterpartyName,
      bin: counterpartyBin,
    },
    amount: Number(raw.amount) || 0,
    vat: raw.vat !== undefined ? Number(raw.vat) : undefined,
    currency: String(raw.currency || 'KZT'),
    status: String(raw.status ?? ''),
    paid_amount:
      raw.paid_amount !== undefined ? Number(raw.paid_amount) : undefined,
    pdf: raw.pdf as string | undefined,
    pdf_downloaded: Boolean(raw.pdf_downloaded),
    pdf_file_path: raw.pdf_file_path as string | undefined,
    items: Array.isArray(raw.items) ? (raw.items as InvoiceItem[]) : [],
    source: (raw.source as string) || 'one_c',
  }
}

function formatInvoiceStatus(
  status: string,
  t: (key: string) => string,
  tStatus: (key: string) => string,
): string {
  const s = String(status).toLowerCase()
  if (s === 'posted' || s === 'true' || s === 'проведен') return t('docStatus.posted')
  if (s === 'false' || s === '') return t('docStatus.draft')
  if (s === 'paid' || s === 'оплачен') return tStatus('status.paid')
  if (s === 'unpaid') return tStatus('status.unpaid')
  if (s === 'overdue') return tStatus('status.overdue')
  return status || '—'
}

// Бейдж как в реестре оплат (mx-badge-*) — только для платёжных статусов,
// у документных (posted/draft) отдельного цвета нигде в приложении нет.
function invoiceStatusBadgeClass(status: string): string | null {
  const s = String(status).toLowerCase()
  if (s === 'paid' || s === 'оплачен') return 'mx-badge-paid'
  if (s === 'unpaid') return 'mx-badge-unpaid'
  if (s === 'overdue') return 'mx-badge-overdue'
  return null
}

// Наименование строки 1С часто нечитаемо (напр. GUID номенклатуры вместо
// описания) — тип счёта считаем по тем же ключевым словам, что и в реестре
// счетов (InvoiceRegistryTable), это надёжнее, чем показывать сырую строку.
function invoiceTypeLabel(invoice: Invoice): string {
  const types = resolveInvoiceServiceTypes({ items: invoice.items })
  if (types.length === 0) return '—'
  return types.map((t) => SERVICE_TYPE_LABELS[t]).join(', ')
}

interface InvoicesListProps {
  period?: string
  /** Только счета этого контрагента (из 1С) */
  counterpartyId?: string
  cacheResetKey?: number
}

export default function InvoicesList({ period, counterpartyId, cacheResetKey }: InvoicesListProps) {
  const t = useTranslations('invoices')
  const tFilters = useTranslations('filters')
  const toast = useToast()
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    if (!getEffectiveTenantId()) {
      setError(t('selectTenantFirst'))
      setInvoices([])
      return
    }
    setError(null)
    setWarning(null)
    try {
      const response = await paymentApi.get1CInvoices(period, 10000, counterpartyId, 'db')
      if (response.error) {
        setError(response.error)
      } else {
        setInvoices(
          (response.invoices || []).map((inv) =>
            normalizeInvoice(inv as Record<string, unknown>)
          )
        )
        if (response.warning) {
          setWarning(response.warning)
        }
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('loadFailed')
      setError(message)
    }
  }, [period, counterpartyId, t])

  const { loading } = useOneCDataLoad(loadData, cacheResetKey)

  const refreshFrom1C = useCallback(async () => {
    if (!period) {
      toast(t('selectPeriodOnRegistry'))
      return
    }
    try {
      const started = await paymentApi.startSyncFrom1C(period)
      if (started.status === 'running') {
        toast(t('syncRunning'))
        return
      }
      const deadline = Date.now() + 180000
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 2500))
        const st = await paymentApi.getSyncStatus(period)
        if (st.status === 'done') {
          await loadData()
          toast(
            st.records != null
              ? t('syncFound', { count: st.records, period })
              : t('syncDone'),
            'success',
          )
          return
        }
        if (st.status === 'failed') {
          toast(t('syncFailed', { error: st.error || t('syncUnknownError') }), 'error')
          return
        }
      }
      toast(t('syncStillRunning'))
    } catch (err) {
      toast(t('syncStartFailed', { error: formatApiError(err) }), 'error')
    }
  }, [period, loadData, toast, t])

  const statusCounts = invoices.reduce(
    (acc, inv) => {
      const s = String(inv.status).toLowerCase()
      if (s === 'paid' || s === 'оплачен') acc.paid += 1
      else if (s === 'unpaid') acc.unpaid += 1
      else if (s === 'overdue') acc.overdue += 1
      return acc
    },
    { paid: 0, unpaid: 0, overdue: 0 },
  )

  const filteredInvoices = invoices.filter((inv) => {
    const q = searchTerm.toLowerCase()
    const name = inv.counterparty_name || inv.counterparty?.name || ''
    const bin = inv.counterparty?.bin || ''
    return (
      inv.number.toLowerCase().includes(q) ||
      name.toLowerCase().includes(q) ||
      bin.includes(searchTerm) ||
      inv.id.toLowerCase().includes(q)
    )
  })

  const handleDownloadPdf = async (invoice: Invoice, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setDownloadingId(invoice.id)
    try {
      let blob: Blob
      if (invoice.source === 'xlsx') {
        // Синтетический id ("xlsx:...") — не настоящий 1С-счёт, отдельный
        // эндпоинт без проверки владения через counterparty_id (см. lib/api.ts).
        blob = await paymentApi.downloadXlsxInvoice(invoice.id)
      } else {
        const cpId = invoice.counterparty_id || invoice.counterparty?.id
        if (!cpId) {
          toast(t('noCounterpartyForDownload'), 'error')
          return
        }
        blob = await paymentApi.download1CInvoice(invoice.id, cpId)
      }
      if (blob.type && blob.type.includes('text')) {
        const text = await blob.text()
        toast(text || t('downloadFailedGeneric'), 'error')
        return
      }
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      // xlsx-строки имеют синтетический id/number вида "xlsx:1:2026-08:cp:rent" —
      // ":" невалиден в имени файла на некоторых ОС, заменяем на "-".
      a.download = `invoice_${(invoice.number || invoice.id).replace(/:/g, '-')}.pdf`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err: unknown) {
      toast(t('downloadFailed', { error: await formatBlobApiError(err) }), 'error')
    } finally {
      setDownloadingId(null)
    }
  }

  const toggleInvoice = (invoiceId: string) => {
    setSelectedInvoiceId((prev) => (prev === invoiceId ? null : invoiceId))
  }

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr)
      return date.toLocaleDateString('ru-RU')
    } catch {
      return dateStr
    }
  }

  const formatCurrency = (amount: number) => {
    return `${new Intl.NumberFormat('ru-RU', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount)} ₸`
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">{t('title')}</h2>
        <TabRefreshButton onClick={refreshFrom1C} loading={loading} />
      </div>

      {invoices.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {statusCounts.paid > 0 && (
            <span className="mx-badge-paid">{t('statusSummary.paid', { count: statusCounts.paid })}</span>
          )}
          {statusCounts.unpaid > 0 && (
            <span className="mx-badge-unpaid">{t('statusSummary.unpaid', { count: statusCounts.unpaid })}</span>
          )}
          {statusCounts.overdue > 0 && (
            <span className="mx-badge-overdue">{t('statusSummary.overdue', { count: statusCounts.overdue })}</span>
          )}
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">
          {error}
        </div>
      )}

      {warning && (
        <div className="mb-4 p-3 bg-amber-50 text-amber-900 border border-amber-200 rounded">
          {warning}
        </div>
      )}

      <div className="mb-4">
        <input
          type="text"
          placeholder={t('searchPlaceholder')}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      {loading && invoices.length === 0 ? (
        <div className="text-center py-8">{t('loading')}</div>
      ) : filteredInvoices.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          {searchTerm ? t('notFound') : t('empty')}
        </div>
      ) : (
        <div className="space-y-4">
          {filteredInvoices.map((invoice) => {
            const isOpen = selectedInvoiceId === invoice.id
            const cpName =
              invoice.counterparty_name || invoice.counterparty?.name || '—'
            return (
            <div
              key={invoice.id}
              role="button"
              tabIndex={0}
              className={`bg-white rounded-[20px] p-4 transition-shadow cursor-pointer select-none ${
                isOpen ? 'ring-2 ring-blue-600 shadow-md' : 'shadow-sm hover:shadow-md'
              }`}
              onClick={() => toggleInvoice(invoice.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  toggleInvoice(invoice.id)
                }
              }}
            >
              <div className="flex justify-between items-start gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold text-gray-900">
                      {invoice.source === 'xlsx'
                        ? t('invoiceNumberXlsx')
                        : t('invoiceNumber', { number: invoice.number })}
                    </h3>
                    <span className="text-sm text-gray-500">
                      {formatDate(invoice.date)}
                    </span>
                    <span className="text-xs text-gray-400">
                      {isOpen ? t('collapse') : t('expand')}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-2">
                    <div className="text-sm">
                      <span className="text-gray-600">{t('counterparty')}</span>
                      <span className="font-medium break-words">{cpName}</span>
                    </div>
                    <div className="text-sm">
                      <span className="text-gray-600">{t('amount')}</span>
                      <span className="font-bold text-blue-700">
                        {formatCurrency(invoice.amount)}
                      </span>
                    </div>
                    <div className="text-sm">
                      <span className="text-gray-600">{t('status')}</span>
                      {invoiceStatusBadgeClass(invoice.status) ? (
                        <span className={invoiceStatusBadgeClass(invoice.status)!}>
                          {formatInvoiceStatus(invoice.status, t, tFilters)}
                        </span>
                      ) : (
                        <span>{formatInvoiceStatus(invoice.status, t, tFilters)}</span>
                      )}
                    </div>
                    <div className="text-sm">
                      <span className="text-gray-600">{t('type')}</span>
                      <span className="font-medium">{invoiceTypeLabel(invoice)}</span>
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={(e) => handleDownloadPdf(invoice, e)}
                  disabled={downloadingId === invoice.id}
                  className="shrink-0 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 text-sm font-medium"
                >
                  {downloadingId === invoice.id ? t('downloadingPdf') : t('downloadPdf')}
                </button>
              </div>

              {isOpen && (
                <div
                  className="mt-4 pt-4 border-t border-gray-200"
                  onClick={(e) => e.stopPropagation()}
                >
                  <p className="text-sm text-gray-600 mb-3">
                    {t(invoice.source === 'xlsx' ? 'recordId' : 'recordIn1c')}
                    <code className="text-xs bg-gray-100 px-1 rounded">{invoice.id}</code>
                  </p>
                  {invoice.items.length > 0 ? (
                    <>
                      <h4 className="font-semibold mb-2">{t('itemsTitle')}</h4>
                      <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 text-sm">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{t('columns.name')}</th>
                              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{t('columns.quantity')}</th>
                              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{t('columns.price')}</th>
                              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{t('columns.amount')}</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-200">
                            {invoice.items.map((item, index) => (
                              <tr key={index}>
                                <td className="px-3 py-2">{item.name}</td>
                                <td className="px-3 py-2">{item.quantity}</td>
                                <td className="px-3 py-2">{formatCurrency(item.price)}</td>
                                <td className="px-3 py-2 font-medium">{formatCurrency(item.amount)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  ) : (
                    <p className="text-sm text-gray-500">
                      {t('noItemsHint')}
                    </p>
                  )}
                </div>
              )}
            </div>
          )})}
        </div>
      )}

      <div className="mt-4 text-sm text-gray-500">
        {t('total', { shown: filteredInvoices.length, total: invoices.length })}
      </div>
    </div>
  )
}
