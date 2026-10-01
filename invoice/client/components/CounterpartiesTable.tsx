'use client'

import { useState, useCallback, useEffect, useRef, useMemo, useDeferredValue } from 'react'
import { useTranslations } from 'next-intl'
import { oneCApi, paymentApi, Counterparty, CounterpartyFolder } from '@/lib/api'
import { catalogApi } from '@/lib/catalogApi'
import { setPaymentTypesEnabled, isPaymentTypeEnabled } from '@/lib/paymentTypesContext'
import { getEffectiveTenantId } from '@/lib/tenantContext'
import NotificationPopover from './NotificationPopover'
import { useOneCDataLoad } from '@/lib/useOneCDataLoad'
import TabRefreshButton from './TabRefreshButton'
import CounterpartyFolderTabs from './CounterpartyFolderTabs'
import { waitForCounterpartySync } from '@/lib/pollCounterpartySync'
import { formatApiError } from '@/lib/notificationHelpers'
import { useToast } from '@/lib/toastContext'
import { useToggleDropdown } from '@/hooks/useToggleDropdown'
import { format, type Locale } from 'date-fns'
import { ru, kk, enUS } from 'date-fns/locale'
import { ChevronLeft, ChevronRight, ChevronDown, Bell, BellOff } from 'lucide-react'

type DebtorServiceTypeFilter = 'all' | 'rent' | 'utilities' | 'operations' | 'signage' | 'assp'

/** Рендерим таблицу постранично — при 10000 контрагентов рендер всех строк
 *  разом (без пагинации/виртуализации) заметно тормозил прокрутку и поиск. */
const PAGE_SIZE = 50

interface CounterpartiesTableProps {
  onSelect?: (counterparty: Counterparty) => void
  locale: string
  cacheResetKey?: number
  paymentStatusFilter?: 'paid' | 'partial' | 'unpaid' | 'overdue' | 'test'
  periodLabel?: string
  period?: string
  /** Диапазон дат счёта (YYYY-MM-DD), из фильтра «Период → Диапазон» */
  dateFrom?: string
  dateTo?: string
  /** Неоплаченные (+просроченные) счета за выбранный период — из карточек аналитики */
  unpaidInvoiceCount?: number
}

const localeMap: Record<string, Locale> = {
  ru: ru,
  kz: kk,
  en: enUS,
}

function formatDisplayDate(dateStr?: string | null, locale?: Locale) {
  if (!dateStr) return '—'
  try {
    return format(new Date(dateStr.split('T')[0]), 'dd.MM.yyyy', { locale })
  } catch {
    return dateStr
  }
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

function formatDisplayDateTime(dateStr?: string | null, locale?: Locale) {
  if (!dateStr) return '—'
  try {
    return format(new Date(dateStr), 'dd.MM.yyyy HH:mm', { locale })
  } catch {
    return dateStr
  }
}

function formatMoneyKzt(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return '—'
  try {
    return `${new Intl.NumberFormat('ru-KZ', {
      maximumFractionDigits: 0,
    }).format(Number(value))} ₸`
  } catch {
    return String(value)
  }
}

function balanceLabelText(label: string | undefined, t: (key: string) => string) {
  if (label === 'debt') return t('balance.debt')
  if (label === 'advance') return t('balance.advance')
  if (label === 'zero') return t('balance.zero')
  return '—'
}

function hasBalanceRow(cp: Counterparty) {
  return (
    cp.balanceDebit !== undefined ||
    cp.balanceCredit !== undefined ||
    cp.balanceNet !== undefined
  )
}

/** для рассылки: если баланс есть — только net > 0 */
function isRealDebtorByBalance(cp: Counterparty) {
  if (!hasBalanceRow(cp)) return true
  return Number(cp.balanceNet || 0) > 1
}

function matchesPaymentStatusFilter(
  cp: Counterparty,
  filter?: CounterpartiesTableProps['paymentStatusFilter'],
): boolean {
  if (!filter) return true
  if (filter === 'test') {
    return cp.fullName.toLowerCase().includes('тест')
  }
  const inv = cp.latestInvoice
  if (!inv) return false
  const status = (inv.paymentStatus || 'unpaid').toLowerCase()
  return status === filter
}

function invoiceDateKey(inv?: { invoiceDate?: string | null; date?: string | null } | null): string {
  const raw = (inv?.invoiceDate || inv?.date || '').toString()
  return raw.split('T')[0].slice(0, 10)
}

function matchesInvoiceDateRange(
  cp: Counterparty,
  dateFrom?: string,
  dateTo?: string,
): boolean {
  if (!dateFrom && !dateTo) return true
  const day = invoiceDateKey(cp.latestInvoice)
  if (!day) return false
  if (dateFrom && day < dateFrom) return false
  if (dateTo && day > dateTo) return false
  return true
}

export default function CounterpartiesTable({
  onSelect,
  locale,
  cacheResetKey,
  paymentStatusFilter,
  periodLabel,
  period,
  dateFrom,
  dateTo,
  unpaidInvoiceCount,
}: CounterpartiesTableProps) {
  const t = useTranslations('registry')
  const tFilters = useTranslations('filters')
  const tCommon = useTranslations('common')
  const tNotify = useTranslations('notifications')
  const toast = useToast()
  const [counterparties, setCounterparties] = useState<Counterparty[]>([])
  const [folders, setFolders] = useState<CounterpartyFolder[]>([])
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [totalFrom1c, setTotalFrom1c] = useState<number | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [bulkSending, setBulkSending] = useState(false)
  const [bulkMessage, setBulkMessage] = useState<string | null>(null)
  const [emailSendingId, setEmailSendingId] = useState<string | null>(null)
  const [autoNotifyTogglingId, setAutoNotifyTogglingId] = useState<string | null>(null)
  const [tenantAutoNotifyPaused, setTenantAutoNotifyPaused] = useState(false)
  const [tenantAutoNotifyToggling, setTenantAutoNotifyToggling] = useState(false)
  const [balanceSyncedAt, setBalanceSyncedAt] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const currentLocale = localeMap[locale] || ru
  const lastPeriodRef = useRef<string | undefined>(undefined)
  // Держит ввод в поле поиска отзывчивым: фильтрация 10к строк идёт по
  // deferred-значению низким приоритетом, не блокируя каждую нажатую клавишу.
  const deferredSearchTerm = useDeferredValue(searchTerm)

  const loadCounterparties = useCallback(async () => {
    const tenantId = getEffectiveTenantId()
    if (!tenantId) {
      setCounterparties([])
      setFolders([])
      return
    }
    setWarning(null)
    try {
      const response = await oneCApi.getCounterparties(10000, {
        include_invoice_status: true,
        period,
      })
      if (!response.error) {
        setPaymentTypesEnabled(
          response.paymentTypesEnabled ||
            response.counterparties?.[0]?.paymentTypesEnabled,
        )
        const list = response.counterparties || []
        setCounterparties(list)
        const fromApi = response.folders || []
        if (fromApi.length > 0) {
          setFolders(fromApi)
        } else {
          const seen = new Map<string, CounterpartyFolder>()
          for (const cp of list) {
            const name = (cp.folderName || '').trim()
            if (!name) continue
            const key = name.toLowerCase()
            if (!seen.has(key)) {
              seen.set(key, { id: cp.folderId, fullName: name })
            }
          }
          setFolders(Array.from(seen.values()).sort((a, b) =>
            a.fullName.localeCompare(b.fullName, 'ru'),
          ))
        }
        setTotalFrom1c(response.total_from_1c ?? list.length ?? null)
        setBalanceSyncedAt(response.balance_synced_at || null)
        setTenantAutoNotifyPaused(Boolean(response.tenantAutoNotifyPaused))
        if (response.sync_error) {
          setWarning(response.sync_error)
        } else if (response.warning) {
          setWarning(response.warning)
        }
      } else if (response.error) {
        setWarning(response.error)
      }
    } catch {
      // ignore load errors
    }
  }, [period])

  const { loading, refresh } = useOneCDataLoad(loadCounterparties, cacheResetKey)

  const refreshFrom1C = useCallback(async () => {
    if (!getEffectiveTenantId()) return
    setSyncing(true)
    setWarning(null)
    try {
      const sync = await oneCApi.syncCounterparties()
      if (!sync.ok) {
        toast(sync.error || t('counterpartiesSyncFailed'), 'error')
        return
      }
      const result = await waitForCounterpartySync({
        limit: 10000,
        period,
        includeInvoiceStatus: true,
      })
      if (result.sync_error) {
        toast(result.sync_error, 'error')
      } else if (result.warning) {
        toast(result.warning, 'error')
      }
      refresh()
    } catch (err: unknown) {
      toast(formatApiError(err), 'error')
    } finally {
      setSyncing(false)
    }
  }, [period, refresh, toast, t])

  useEffect(() => {
    if (lastPeriodRef.current === undefined) {
      lastPeriodRef.current = period
      return
    }
    if (lastPeriodRef.current !== period) {
      lastPeriodRef.current = period
      refresh()
    }
  }, [period, refresh])

  // Пересчитываем только когда реально меняются исходные данные/фильтры, а не
  // на каждый рендер (10к контрагентов × filter — не бесплатно). Раньше это
  // пересчитывалось заново даже на несвязанные апдейты состояния (например,
  // emailSendingId при отправке письма одному контрагенту).
  const registryCounterparties = useMemo(
    () => counterparties.filter((cp) => Boolean(cp.latestInvoice) || (cp.invoiceCount ?? 0) > 0),
    [counterparties],
  )

  const filteredCounterparties = useMemo(
    () =>
      registryCounterparties.filter((cp) => {
        if (selectedFolder) {
          const folder = (cp.folderName || '').trim()
          if (folder.toLowerCase() !== selectedFolder.toLowerCase()) return false
        }
        const term = deferredSearchTerm.toLowerCase()
        return (
          matchesInvoiceDateRange(cp, dateFrom, dateTo) &&
          matchesPaymentStatusFilter(cp, paymentStatusFilter) &&
          (cp.fullName.toLowerCase().includes(term) ||
            cp.bin?.toLowerCase().includes(term) ||
            cp.iin?.toLowerCase().includes(term) ||
            (cp.phoneNumber || cp.phone || '').includes(deferredSearchTerm) ||
            (cp.email || '').toLowerCase().includes(term))
        )
      }),
    [registryCounterparties, selectedFolder, dateFrom, dateTo, paymentStatusFilter, deferredSearchTerm],
  )

  const totalPages = Math.max(1, Math.ceil(filteredCounterparties.length / PAGE_SIZE))
  const pagedCounterparties = useMemo(
    () => filteredCounterparties.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [filteredCounterparties, currentPage],
  )

  // Список фильтров сузился — возвращаемся на первую страницу, чтобы не
  // залипнуть на пустой странице №8 из старой, более длинной выдачи.
  useEffect(() => {
    setCurrentPage(1)
  }, [selectedFolder, dateFrom, dateTo, paymentStatusFilter, deferredSearchTerm])

  // неоплаченные счета за период; если есть balance — только с net > 0
  const hasAnyBalance = useMemo(
    () => registryCounterparties.some(hasBalanceRow),
    [registryCounterparties],
  )
  const periodDebtorCount = useMemo(
    () =>
      registryCounterparties.filter(
        (cp) =>
          matchesInvoiceDateRange(cp, dateFrom, dateTo) &&
          (cp.latestInvoice?.paymentStatus || 'unpaid').toLowerCase() !== 'paid' &&
          isRealDebtorByBalance(cp),
      ).length,
    [registryCounterparties, dateFrom, dateTo],
  )
  // Тот же список, но без фильтра по net из баланса 1С — сколько всего
  // счетов со статусом "не оплачен"/"просрочен" за период, независимо от
  // того, что 1С показывает по авансу. Используется опт-ин чекбоксом ниже —
  // на случай, если баланс 1С не отражает реальный долг по конкретному счёту
  // (открытый вопрос по надёжности данных некоторых ТРЦ).
  const periodDebtorCountNoBalance = useMemo(
    () =>
      registryCounterparties.filter(
        (cp) =>
          matchesInvoiceDateRange(cp, dateFrom, dateTo) &&
          (cp.latestInvoice?.paymentStatus || 'unpaid').toLowerCase() !== 'paid',
      ).length,
    [registryCounterparties, dateFrom, dateTo],
  )
  const allUnpaidCount =
    typeof unpaidInvoiceCount === 'number' ? unpaidInvoiceCount : periodDebtorCountNoBalance
  const [ignoreBalanceFilter, setIgnoreBalanceFilter] = useState(false)
  const [serviceTypeFilter, setServiceTypeFilter] = useState<DebtorServiceTypeFilter>('all')
  const { toggle: toggleDebtorSendMenu, isOpen: isDebtorSendMenuOpen, close: closeDebtorSendMenu } =
    useToggleDropdown()
  const debtorSendCount = ignoreBalanceFilter
    ? allUnpaidCount
    : hasAnyBalance
      ? periodDebtorCount
      : allUnpaidCount
  const debtorServiceTypeOptions: {
    key: 'rent' | 'utilities' | 'operations' | 'signage' | 'assp'
    label: string
  }[] = []
  if (isPaymentTypeEnabled('rent')) debtorServiceTypeOptions.push({ key: 'rent', label: t('serviceType.rent') })
  if (isPaymentTypeEnabled('utilities'))
    debtorServiceTypeOptions.push({ key: 'utilities', label: t('serviceType.utilities') })
  if (isPaymentTypeEnabled('operations'))
    debtorServiceTypeOptions.push({ key: 'operations', label: t('serviceType.operations') })
  if (isPaymentTypeEnabled('signage'))
    debtorServiceTypeOptions.push({ key: 'signage', label: t('serviceType.signage') })
  if (isPaymentTypeEnabled('assp'))
    debtorServiceTypeOptions.push({ key: 'assp', label: t('serviceType.assp') })
  const debtorAudienceLabel = ignoreBalanceFilter ? t('sendButtonAllUnpaid') : t('sendButtonDebtorsOnly')
  const debtorServiceTypeSuffix =
    serviceTypeFilter === 'all' ? '' : ` · ${t(`serviceType.${serviceTypeFilter}`)}`
  const debtorSendButtonText = bulkSending
    ? t('sendingDebtors')
    : `${debtorAudienceLabel}${debtorServiceTypeSuffix}${debtorSendCount ? ` (${debtorSendCount})` : ''}`

  const sendAllDebtors = useCallback(async () => {
    if (!getEffectiveTenantId()) return
    if (!period && !(dateFrom && dateTo)) {
      setBulkMessage(t('selectPeriodFirst'))
      return
    }
    closeDebtorSendMenu()
    const scope =
      dateFrom && dateTo
        ? t('sendDebtorsConfirmScopeRange', { from: dateFrom, to: dateTo })
        : t('sendDebtorsConfirmScopePeriod', { period })
    if (
      !window.confirm(
        t('sendDebtorsConfirm', {
          scope,
          serviceTypeNote:
            serviceTypeFilter === 'all'
              ? ''
              : t('sendDebtorsConfirmServiceTypeNote', {
                  type: t(`serviceType.${serviceTypeFilter}`),
                }),
          balanceNote: ignoreBalanceFilter
            ? t('sendDebtorsConfirmIgnoreBalanceNote')
            : hasAnyBalance
              ? t('sendDebtorsConfirmBalanceNote')
              : '',
          countNote: debtorSendCount ? t('sendDebtorsConfirmCountNote', { count: debtorSendCount }) : '',
        }),
      )
    ) {
      return
    }
    setBulkSending(true)
    setBulkMessage(null)
    try {
      const result = await paymentApi.sendDebtorsBulk({
        ...(dateFrom && dateTo
          ? { date_from: dateFrom, date_to: dateTo }
          : { period: period || undefined }),
        ...(ignoreBalanceFilter ? { ignore_balance_filter: true } : {}),
        ...(serviceTypeFilter !== 'all' ? { service_types: [serviceTypeFilter] } : {}),
      })
      setBulkMessage(result.message || t('queuedCount', { count: result.queued }))
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t('debtorsSendFailed')
      setBulkMessage(typeof detail === 'string' ? detail : t('debtorsSendFailed'))
    } finally {
      setBulkSending(false)
    }
  }, [
    period,
    dateFrom,
    dateTo,
    debtorSendCount,
    hasAnyBalance,
    ignoreBalanceFilter,
    serviceTypeFilter,
    closeDebtorSendMenu,
    t,
  ])

  const handleSendInvoiceEmail = useCallback(async (cp: Counterparty, e: React.MouseEvent) => {
    e.stopPropagation()
    const email = (cp.email || '').trim()
    if (!email || !cp.id) return
    if (
      !window.confirm(
        t('sendEmailConfirm', { email, name: cp.fullName }),
      )
    ) {
      return
    }
    setEmailSendingId(cp.id)
    try {
      const result = await paymentApi.sendInvoiceEmail({
        counterpartyId: cp.id,
        email,
        invoiceId: cp.latestInvoice?.invoiceId || undefined,
        counterpartyName: cp.fullName,
      })
      toast(result.message || t('invoiceSentToEmail', { email }), 'success')
    } catch (err: unknown) {
      toast(t('emailSendError', { error: formatApiError(err) }), 'error')
    } finally {
      setEmailSendingId(null)
    }
  }, [toast, t])

  const handleToggleAutoNotify = useCallback(async (cp: Counterparty, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!cp.id || autoNotifyTogglingId) return
    const nextPaused = !cp.autoNotifyPaused
    setAutoNotifyTogglingId(cp.id)
    // Оптимистично — иначе клик по кнопке в списке из 10к строк ждёт round-trip.
    setCounterparties((prev) =>
      prev.map((item) => (item.id === cp.id ? { ...item, autoNotifyPaused: nextPaused } : item)),
    )
    try {
      await catalogApi.setAutoNotifyPaused(cp.id, nextPaused, cp.fullName)
    } catch (err: unknown) {
      // откат при ошибке
      setCounterparties((prev) =>
        prev.map((item) => (item.id === cp.id ? { ...item, autoNotifyPaused: !nextPaused } : item)),
      )
      toast(t('autoNotifyToggleError', { error: formatApiError(err) }), 'error')
    } finally {
      setAutoNotifyTogglingId(null)
    }
  }, [autoNotifyTogglingId, toast, t])

  const handleToggleTenantAutoNotify = useCallback(async () => {
    if (tenantAutoNotifyToggling) return
    const nextPaused = !tenantAutoNotifyPaused
    if (nextPaused && !window.confirm(t('stopAllAutoNotifyConfirm'))) {
      return
    }
    setTenantAutoNotifyToggling(true)
    setTenantAutoNotifyPaused(nextPaused)
    try {
      await catalogApi.setTenantAutoNotifyPaused(nextPaused)
    } catch (err: unknown) {
      setTenantAutoNotifyPaused(!nextPaused)
      toast(t('autoNotifyToggleError', { error: formatApiError(err) }), 'error')
    } finally {
      setTenantAutoNotifyToggling(false)
    }
  }, [tenantAutoNotifyPaused, tenantAutoNotifyToggling, toast, t])

  if (!getEffectiveTenantId()) {
    return (
      <div className="card">
        <p className="title">{t('notConnectedTitle')}</p>
        <p className="subtitle">
          {t('notConnectedSubtitle')}
        </p>
      </div>
    )
  }

  if (loading && counterparties.length === 0 && !syncing) {
    return (
      <div className="card columns-3">
        <p className="title">{t('loading')}</p>
      </div>
    )
  }

  return (
    <div className="card columns-3">
      {/* Выбор папки 1С — над заголовком «Статус платежей»; скрыт, пока folders пустой */}
      <CounterpartyFolderTabs
        folders={folders}
        selected={selectedFolder}
        onSelect={setSelectedFolder}
      />
      <div className="row space">
        <div className="card_title">
          <p className="title">{t('title')}</p>
          <p className="subtitle">{periodLabel || tFilters('currentPeriod')}</p>
        </div>

        <div className="col">
          <div className="row gap-4 end">
            <div className="input size-s secondary rounded">
              <input
                type="text"
                placeholder={t('searchPlaceholder')}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <div className="row gap-0" style={{ position: 'relative' }}>
              <button
                type="button"
                className="button size-m color-green"
                onClick={sendAllDebtors}
                disabled={bulkSending || syncing || loading || (!period && !(dateFrom && dateTo))}
                style={{ borderTopRightRadius: 0, borderBottomRightRadius: 0 }}
              >
                {debtorSendButtonText}
              </button>
              <button
                type="button"
                className="button size-m color-green toggle_handler"
                onClick={toggleDebtorSendMenu('debtorSend')}
                disabled={bulkSending}
                aria-label={t('sendMenuTypeHeading')}
                title={t('sendMenuTypeHeading')}
                style={{
                  borderTopLeftRadius: 0,
                  borderBottomLeftRadius: 0,
                  paddingLeft: 8,
                  paddingRight: 8,
                  borderLeft: '1px solid rgba(255,255,255,0.35)',
                }}
              >
                <ChevronDown
                  size={16}
                  style={{
                    transition: 'transform 0.1s ease',
                    transform: isDebtorSendMenuOpen('debtorSend') ? 'rotate(180deg)' : undefined,
                  }}
                />
              </button>
              <div
                className={`toggle_content from_right auto_dismiss${isDebtorSendMenuOpen('debtorSend') ? ' is-open' : ''}`}
                onClick={(e) => e.stopPropagation()}
                style={{ width: 320, maxHeight: 'none', overflow: 'visible' }}
              >
                <div className="column gap-s pv-8 ph-16" style={{ borderBottom: '1px solid #eae6f5' }}>
                  <p className="subtitle" style={{ margin: 0 }}>
                    {t('sendMenuRecipientsLabel')}
                  </p>
                  <p style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
                    {debtorSendCount ? t('sendMenuRecipientsCount', { count: debtorSendCount }) : t('sendMenuRecipientsNone')}
                  </p>
                </div>

                <div className="column gap-s pv-8 ph-16">
                  <p className="subtitle" style={{ margin: 0 }}>{t('sendMenuTypeHeading')}</p>
                  <div className="row gap-xs" style={{ flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className={`button size-s ${serviceTypeFilter === 'all' ? 'color-green' : 'color-gray'}`}
                      onClick={() => setServiceTypeFilter('all')}
                      disabled={bulkSending}
                    >
                      {t('sendMenuAllTypes')}
                    </button>
                    {debtorServiceTypeOptions.map((opt) => (
                      <button
                        key={opt.key}
                        type="button"
                        className={`button size-s ${serviceTypeFilter === opt.key ? 'color-green' : 'color-gray'}`}
                        onClick={() => setServiceTypeFilter(opt.key)}
                        disabled={bulkSending}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {hasAnyBalance && (
                  <div className="column gap-s pv-8 ph-16">
                    <p className="subtitle" style={{ margin: 0 }}>{t('sendMenuAudienceHeading')}</p>
                    <label className="radio circle" title={t('sendMenuAudienceDebtorsOnlyHint')}>
                      <input
                        type="radio"
                        name="debtor-send-audience"
                        checked={!ignoreBalanceFilter}
                        onChange={() => setIgnoreBalanceFilter(false)}
                        disabled={bulkSending}
                      />
                      <span className="checkmark" />
                      <span>{t('sendMenuAudienceDebtorsOnly')}</span>
                    </label>
                    <label className="radio circle" title={t('sendMenuAudienceAllUnpaidHint')}>
                      <input
                        type="radio"
                        name="debtor-send-audience"
                        checked={ignoreBalanceFilter}
                        onChange={() => setIgnoreBalanceFilter(true)}
                        disabled={bulkSending}
                      />
                      <span className="checkmark" />
                      <span>{t('sendMenuAudienceAllUnpaid')}</span>
                    </label>
                  </div>
                )}
              </div>
            </div>
            <TabRefreshButton
              onClick={refreshFrom1C}
              loading={syncing || loading}
            />
            <button
              type="button"
              className="button size-m color-gray"
              onClick={handleToggleTenantAutoNotify}
              disabled={tenantAutoNotifyToggling}
              title={
                tenantAutoNotifyPaused
                  ? t('resumeAllAutoNotifyTooltip')
                  : t('stopAllAutoNotifyTooltip')
              }
            >
              {tenantAutoNotifyPaused ? t('resumeAllAutoNotify') : t('stopAllAutoNotify')}
            </button>
          </div>
        </div>
      </div>

      {bulkMessage && (
        <p className="subtitle" style={{ color: '#166534', padding: '0 16px' }}>
          {bulkMessage}
        </p>
      )}

      {tenantAutoNotifyPaused && (
        <p className="subtitle" style={{ color: '#b45309', padding: '0 16px' }}>
          {t('allAutoNotifyPausedBanner')}
        </p>
      )}

      {warning && (
        <p className="subtitle" style={{ color: '#b45309', padding: '0 16px' }}>
          {warning}
        </p>
      )}

      {syncing && (
        <p className="subtitle" style={{ padding: '0 16px' }}>
          {t('syncingHint')}
        </p>
      )}

      {balanceSyncedAt && (
        <p className="subtitle" style={{ padding: '0 16px' }}>
          {t('balanceSyncedAt', { date: formatDisplayDate(balanceSyncedAt.slice(0, 10), currentLocale) })}
        </p>
      )}

      <table className="style-white" cellSpacing={0}>
        <tbody>
          <tr>
            <th className="medium">{t('columns.counterparty')}</th>
            <th className="medium">{t('columns.binIin')}</th>
            <th className="medium">{t('columns.phone')}</th>
            <th className="medium">{t('columns.email')}</th>
            <th className="medium" title={t('debtTooltip')}>
              {t('columns.debt')}
            </th>
            <th className="medium" title={t('advanceTooltip')}>
              {t('columns.advance')}
            </th>
            <th className="medium" title={t('netTooltip')}>
              {t('columns.net')}
            </th>
            <th className="medium">{t('columns.notifications')}</th>
            <th className="medium">{t('columns.lastReminder')}</th>
            <th className="medium">{t('columns.invoiceDate')}</th>
            <th className="medium">{t('columns.dueDate')}</th>
            <th className="medium">{t('columns.status')}</th>
            <th className="medium">{t('columns.paidAt')}</th>
          </tr>
          {pagedCounterparties.length === 0 ? (
            <tr>
              <td colSpan={13} className="medium">
                {searchTerm ? t('notFound') : t('empty')}
              </td>
            </tr>
          ) : (
            pagedCounterparties.map((counterparty) => {
              const phone = counterparty.phoneNumber || counterparty.phone || ''
              const email = (counterparty.email || '').trim()
              const binOrIin = counterparty.bin || counterparty.iin || '—'
              const inv = counterparty.latestInvoice
              const rentDueDay = counterparty.paymentDueDays?.rent ?? 5
              const utilitiesDueDay = counterparty.paymentDueDays?.utilities ?? 5
              const operationsDueDay = counterparty.paymentDueDays?.operations ?? 5
              const balOk = hasBalanceRow(counterparty)
              return (
                <tr
                  key={counterparty.id}
                  className={`cursor-pointer ${paymentRowClass(inv?.paymentStatus)}`}
                  onClick={() => onSelect?.(counterparty)}
                >
                  <td className="medium" title={counterparty.fullName}>
                    <div>{counterparty.fullName}</div>
                    {counterparty.contactPerson && (
                      <p className="subtitle">{t('contact', { name: counterparty.contactPerson })}</p>
                    )}
                  </td>
                  <td>{binOrIin}</td>
                  <td>{phone || '—'}</td>
                  <td
                    onClick={(e) => e.stopPropagation()}
                    title={email ? tNotify('emailTitle', { email }) : undefined}
                  >
                    {email ? (
                      <button
                        type="button"
                        className="button size-s color-green"
                        style={{ maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis' }}
                        onClick={(e) => handleSendInvoiceEmail(counterparty, e)}
                        disabled={emailSendingId === counterparty.id}
                      >
                        {emailSendingId === counterparty.id ? tCommon('sending') : email}
                      </button>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td
                    className="medium"
                    style={{
                      textAlign: 'right',
                      whiteSpace: 'nowrap',
                      fontWeight: balOk && Number(counterparty.balanceDebit || 0) > 1 ? 600 : undefined,
                      color: balOk && Number(counterparty.balanceDebit || 0) > 1 ? '#b45309' : undefined,
                    }}
                  >
                    {balOk ? formatMoneyKzt(counterparty.balanceDebit) : '—'}
                  </td>
                  <td
                    className="medium"
                    style={{
                      textAlign: 'right',
                      whiteSpace: 'nowrap',
                      color: balOk && Number(counterparty.balanceCredit || 0) > 1 ? '#1d4ed8' : undefined,
                    }}
                  >
                    {balOk ? formatMoneyKzt(counterparty.balanceCredit) : '—'}
                  </td>
                  <td
                    className="medium"
                    style={{
                      textAlign: 'right',
                      whiteSpace: 'nowrap',
                      fontWeight: 600,
                      color:
                        balOk && Number(counterparty.balanceNet || 0) > 1
                          ? '#b45309'
                          : balOk && Number(counterparty.balanceCredit || 0) > 1
                            ? '#1d4ed8'
                            : undefined,
                    }}
                  >
                    {balOk ? formatMoneyKzt(counterparty.balanceNet) : '—'}
                    {balOk && counterparty.balanceLabel && counterparty.balanceLabel !== 'zero' && (
                      <span style={{ fontWeight: 400, opacity: 0.75 }}>
                        {' '}
                        ({balanceLabelText(counterparty.balanceLabel, t)})
                      </span>
                    )}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="row gap-4" style={{ alignItems: 'center' }}>
                      {phone || email ? (
                        <NotificationPopover
                          counterparty={counterparty}
                          phoneNumber={phone || undefined}
                          paymentStatus={inv?.paymentStatus}
                        />
                      ) : (
                        '—'
                      )}
                      <button
                        type="button"
                        className="rounded-full p-1 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                        onClick={(e) => handleToggleAutoNotify(counterparty, e)}
                        disabled={autoNotifyTogglingId === counterparty.id}
                        title={
                          counterparty.autoNotifyPaused
                            ? t('resumeAutoNotifyTooltip')
                            : t('stopAutoNotifyTooltip')
                        }
                        aria-label={
                          counterparty.autoNotifyPaused ? t('resumeAutoNotify') : t('stopAutoNotify')
                        }
                      >
                        {counterparty.autoNotifyPaused ? (
                          <BellOff size={16} style={{ color: '#b45309' }} />
                        ) : (
                          <Bell size={16} style={{ opacity: 0.6 }} />
                        )}
                      </button>
                    </div>
                  </td>
                  <td
                    className="whitespace-nowrap"
                    title={t('lastReminderTooltip')}
                  >
                    {formatDisplayDateTime(counterparty.lastWhatsappSentAt, currentLocale)}
                  </td>
                  <td>{formatDisplayDate(inv?.invoiceDate, currentLocale)}</td>
                  <td>
                    {isPaymentTypeEnabled('rent') && (
                      <div>{t('dueDays.rent', { day: rentDueDay })}</div>
                    )}
                    {isPaymentTypeEnabled('utilities') && (
                      <div>{t('dueDays.utilities', { day: utilitiesDueDay })}</div>
                    )}
                    {isPaymentTypeEnabled('operations') && (
                      <div>{t('dueDays.operations', { day: operationsDueDay })}</div>
                    )}
                  </td>
                  <td>
                    {inv ? (
                      <span
                        className={`${paymentStatusBadgeClass(inv.paymentStatus || 'unpaid')} whitespace-nowrap`}
                      >
                        {paymentStatusLabel(inv.paymentStatus || 'unpaid', tFilters)}
                      </span>
                    ) : (
                      <span className="subtitle">{t('noInvoice')}</span>
                    )}
                  </td>
                  <td>{formatDisplayDate(inv?.paidAt, currentLocale)}</td>
                </tr>
              )
            })
          )}
        </tbody>
      </table>

      <div className="row space" style={{ alignItems: 'center' }}>
        <p className="subtitle">
          {t('shownRange', {
            from: pagedCounterparties.length ? (currentPage - 1) * PAGE_SIZE + 1 : 0,
            to: (currentPage - 1) * PAGE_SIZE + pagedCounterparties.length,
            total: filteredCounterparties.length,
            registryTotal: registryCounterparties.length,
          })}
          {totalFrom1c != null && totalFrom1c !== counterparties.length && (
            <span>{t('catalogTotal', { total: totalFrom1c })}</span>
          )}
        </p>

        {totalPages > 1 && (
          <div className="row gap-4" style={{ alignItems: 'center' }}>
            <button
              type="button"
              className="mx-pagination-item disabled:opacity-40 disabled:cursor-not-allowed"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              aria-label={t('prevPage')}
            >
              <ChevronLeft size={18} />
            </button>
            <span className="subtitle">
              {currentPage} / {totalPages}
            </span>
            <button
              type="button"
              className="mx-pagination-item disabled:opacity-40 disabled:cursor-not-allowed"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              aria-label={t('nextPage')}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
