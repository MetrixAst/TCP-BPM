'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { paymentApi, oneCApi, Payment, Counterparty, PaymentAnalytics } from '@/lib/api'
import { useOneCDataLoad } from '@/lib/useOneCDataLoad'
import AnalyticsCards from './AnalyticsCards'
import NotificationPopover from './NotificationPopover'
import TabRefreshButton from './TabRefreshButton'
import { formatServiceTypeLabel, InvoiceServiceType } from '@/lib/counterpartyPhoneUtils'
import { enabledPaymentTypes, ALWAYS_VISIBLE_PAYMENT_TYPES } from '@/lib/paymentTypesContext'
import { format, type Locale } from 'date-fns'
import { ru, kk, enUS } from 'date-fns/locale'
import { ChevronLeft, ChevronRight } from 'lucide-react'

/** Один ряд = один счёт, а не контрагент — старая CounterpartiesTable
 * показывала контрагенту только один "самый срочный" счёт, остальные его
 * счета за период были не видны, хотя фильтры (Оплачено/Не оплачено/...)
 * обещают фильтровать именно счета. См. обсуждение редизайна от 2026-08-25. */
const PAGE_SIZE = 20

type StatusFilterValue = 'paid' | 'partial' | 'unpaid' | 'overdue' | undefined
type ServiceTypeFilterValue = InvoiceServiceType | undefined

const localeMap: Record<string, Locale> = {
  ru,
  kz: kk,
  en: enUS,
}

interface InvoiceRegistryTableProps {
  locale: string
  cacheResetKey?: number
  period?: string
  dateFrom?: string
  dateTo?: string
  periodLabel?: string
}

function formatDisplayDate(dateStr?: string | null, locale?: Locale) {
  if (!dateStr) return '—'
  try {
    return format(new Date(dateStr.split('T')[0]), 'dd.MM.yyyy', { locale })
  } catch {
    return dateStr
  }
}

function formatDisplayDateTime(dateStr?: string | null, locale?: Locale) {
  if (!dateStr) return '—'
  try {
    return format(new Date(dateStr), 'dd.MM.yyyy HH:mm', { locale })
  } catch {
    return dateStr
  }
}

function lastReminderAt(payment: Payment): string | null {
  const notifications = payment.notifications || []
  let latest: string | null = null
  for (const n of notifications) {
    if (n.sent_at && (!latest || n.sent_at > latest)) latest = n.sent_at
  }
  return latest
}

function paymentStatusBadgeClass(status: string) {
  const s = status.toLowerCase()
  const map: Record<string, string> = {
    paid: 'mx-badge-paid',
    partial: 'mx-badge-partial',
    unpaid: 'mx-badge-unpaid',
    overdue: 'mx-badge-overdue',
  }
  return map[s] || 'mx-badge-unpaid'
}

function paymentRowClass(status?: string) {
  const s = (status || '').toLowerCase()
  const map: Record<string, string> = {
    paid: 'mx-row-paid',
    partial: 'mx-row-partial',
    unpaid: 'mx-row-unpaid',
    overdue: 'mx-row-overdue',
  }
  return map[s] || ''
}

function paymentStatusLabel(status: string, t: (key: string) => string) {
  const s = status.toLowerCase()
  if (['paid', 'partial', 'unpaid', 'overdue'].includes(s)) {
    return t(`status.${s}`)
  }
  return status
}

export default function InvoiceRegistryTable({
  locale,
  cacheResetKey,
  period,
  dateFrom,
  dateTo,
  periodLabel,
}: InvoiceRegistryTableProps) {
  const t = useTranslations('invoiceRegistry')
  const tFilters = useTranslations('filters')
  const currentLocale = localeMap[locale] || ru

  const [payments, setPayments] = useState<Payment[]>([])
  const [counterpartiesById, setCounterpartiesById] = useState<Record<string, Counterparty>>({})
  const [analytics, setAnalytics] = useState<PaymentAnalytics | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilterValue>(undefined)
  const [serviceTypeFilter, setServiceTypeFilter] = useState<ServiceTypeFilterValue>(undefined)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoadError(null)
    const [paymentsResult, analyticsResult, counterpartiesResult] = await Promise.allSettled([
      paymentApi.getPayments({
        period,
        date_from: dateFrom,
        date_to: dateTo,
        status: statusFilter,
        service_type: serviceTypeFilter,
        page,
        page_size: PAGE_SIZE,
      }),
      paymentApi.getAnalytics({ period, date_from: dateFrom, date_to: dateTo }),
      oneCApi.getCounterparties(10000),
    ])

    if (paymentsResult.status === 'fulfilled') {
      setPayments(paymentsResult.value.items)
      setTotal(paymentsResult.value.total)
      setTotalPages(paymentsResult.value.total_pages || 1)
    } else {
      setLoadError(t('loadFailed'))
    }
    if (analyticsResult.status === 'fulfilled') {
      setAnalytics(analyticsResult.value)
    }
    if (counterpartiesResult.status === 'fulfilled') {
      const map: Record<string, Counterparty> = {}
      for (const cp of counterpartiesResult.value.counterparties || []) {
        map[cp.id.toLowerCase()] = cp
      }
      setCounterpartiesById(map)
    }
  }, [period, dateFrom, dateTo, statusFilter, serviceTypeFilter, page, t])

  const { loading, refresh } = useOneCDataLoad(load, cacheResetKey)

  // Перезагрузка при смене фильтров/страницы — но не в момент монтирования
  // (useOneCDataLoad уже сам грузит один раз при монтировании).
  const filtersSyncRef = useRef(false)
  useEffect(() => {
    if (!filtersSyncRef.current) {
      filtersSyncRef.current = true
      return
    }
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, dateFrom, dateTo, statusFilter, serviceTypeFilter, page])

  // Смена фильтра типа/статуса — сбрасываем на первую страницу.
  useEffect(() => {
    setPage(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, serviceTypeFilter, period, dateFrom, dateTo])

  // rent/utilities/operations всегда в списке (скрыть их при 0 счетов выглядело
  // бы как баг — "куда делась аренда?"). Остальные (вывеска/АССП/долг/прочее) —
  // длинный хвост, актуальный не для каждого ТЦ/периода: показываем только
  // когда для них правда есть хотя бы один счёт (analytics.service_types_present,
  // независимо от текущего фильтра — см. бэкенд, _service_types_present).
  // Уже выбранный тип не прячем даже с 0 — иначе select молча остался бы с
  // невидимым текущим значением.
  const presentTypes = new Set(analytics?.service_types_present || [])
  const serviceTypeOptions = enabledPaymentTypes().filter(
    (type) =>
      ALWAYS_VISIBLE_PAYMENT_TYPES.includes(type) ||
      presentTypes.has(type) ||
      type === serviceTypeFilter,
  )

  return (
    <div className="column gap-s">
      <div className="row space" style={{ alignItems: 'center' }}>
        <p className="subtitle">{periodLabel || tFilters('currentPeriod')}</p>
        <TabRefreshButton onClick={refresh} loading={loading} />
      </div>

      {analytics && (
        <AnalyticsCards
          analytics={analytics}
          activeStatus={statusFilter}
          onSelectStatus={setStatusFilter}
        />
      )}

      <div className="row gap-s" style={{ alignItems: 'center' }}>
        <label className="subtitle">{t('serviceTypeLabel')}</label>
        <select
          className="select"
          value={serviceTypeFilter || ''}
          onChange={(e) =>
            setServiceTypeFilter((e.target.value || undefined) as ServiceTypeFilterValue)
          }
        >
          <option value="">{t('allServiceTypes')}</option>
          {serviceTypeOptions.map((type) => (
            <option key={type} value={type}>
              {t(`serviceType.${type}`)}
            </option>
          ))}
        </select>
      </div>

      {loadError && <div className="card"><p className="title">{loadError}</p></div>}

      <table className="mx-table">
        <thead>
          <tr>
            <th className="medium">{t('columns.counterparty')}</th>
            <th className="medium">{t('columns.serviceType')}</th>
            <th className="medium">{t('columns.phone')}</th>
            <th className="medium">{t('columns.binIin')}</th>
            <th className="medium">{t('columns.lastReminder')}</th>
            <th className="medium">{t('columns.dueDate')}</th>
            <th className="medium">{t('columns.paidAt')}</th>
            <th className="medium">{t('columns.status')}</th>
            <th className="medium">{t('columns.actions')}</th>
          </tr>
        </thead>
        <tbody>
          {loading && payments.length === 0 ? (
            <tr>
              <td colSpan={9} className="medium">
                {t('loading')}
              </td>
            </tr>
          ) : payments.length === 0 ? (
            <tr>
              <td colSpan={9} className="medium">
                {t('empty')}
              </td>
            </tr>
          ) : (
            payments.map((payment) => {
              const counterparty = payment.counterparty_id
                ? counterpartiesById[payment.counterparty_id.toLowerCase()]
                : undefined
              const phone = counterparty?.phoneNumber || counterparty?.phone || ''
              const binOrIin = counterparty?.bin || counterparty?.iin || '—'
              const reminder = lastReminderAt(payment)
              // payment.tenant_name иногда содержит сырой GUID контрагента
              // вместо имени — 1С не всегда возвращает КонтрагентПредставление
              // для "заглушек" (см. app/api/notifications.py: tenant_name =
              // counterparty_name or counterparty_id при первом "Отправить" по
              // ещё не синканному счёту). Каталог контрагентов (тот же, что
              // даёт телефон/БИН выше) обычно содержит настоящее имя — им и
              // подписываем ряд, sync потом либо подтвердит его, либо заменит.
              const displayName = counterparty?.fullName || payment.tenant_name || '—'
              return (
                <tr key={payment.id} className={paymentRowClass(payment.status)}>
                  <td className="medium" title={displayName}>
                    {displayName}
                  </td>
                  <td>{formatServiceTypeLabel(payment.service_type)}</td>
                  <td>{phone || '—'}</td>
                  <td>{binOrIin}</td>
                  <td className="whitespace-nowrap">
                    {reminder ? formatDisplayDateTime(reminder, currentLocale) : '—'}
                  </td>
                  <td>{formatDisplayDate(payment.due_date, currentLocale)}</td>
                  <td>{formatDisplayDate(payment.paid_at, currentLocale)}</td>
                  <td>
                    <span className={`${paymentStatusBadgeClass(payment.status)} whitespace-nowrap`}>
                      {paymentStatusLabel(payment.status, tFilters)}
                    </span>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    {phone || payment.counterparty_id ? (
                      <NotificationPopover
                        payment={payment}
                        counterparty={counterparty}
                        phoneNumber={phone || undefined}
                        paymentStatus={payment.status}
                      />
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              )
            })
          )}
        </tbody>
      </table>

      <div className="row space" style={{ alignItems: 'center' }}>
        <p className="subtitle">
          {t('shownRange', {
            from: payments.length ? (page - 1) * PAGE_SIZE + 1 : 0,
            to: (page - 1) * PAGE_SIZE + payments.length,
            total,
          })}
        </p>
        <div className="row gap-s" style={{ alignItems: 'center' }}>
          <button
            type="button"
            className="button size-s"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            aria-label={t('prevPage')}
          >
            <ChevronLeft size={16} />
          </button>
          <span className="subtitle">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            className="button size-s"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            aria-label={t('nextPage')}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
