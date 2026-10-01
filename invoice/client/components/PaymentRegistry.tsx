'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'next/navigation'
import { useRouter, usePathname } from '@/i18n/routing'
import { paymentApi, oneCApi, Payment, PaymentFilter, PaymentAnalytics, Counterparty } from '@/lib/api'
import { useOneCDataLoad } from '@/lib/useOneCDataLoad'
import Filters from './Filters'
import AnalyticsCards from './AnalyticsCards'
import Header from './Header'
import OneCDownloadModal from './OneCDownloadModal'
import CounterpartiesList from './CounterpartiesList'
import CounterpartyBalance from './CounterpartyBalance'
import CounterpartyDetails from './CounterpartyDetails'
import InvoicesList from './InvoicesList'
import CounterpartiesTable from './CounterpartiesTable'
import InvoiceRegistryTable from './InvoiceRegistryTable'
import TenantContextSelector from './TenantContextSelector'
import CatalogTenantsList from './CatalogTenantsList'
import XlsxUploadPanel from './XlsxUploadPanel'
import { isPortalSession } from '@/lib/tenantContext'
import { getPortalSession } from '@/lib/tenantAuth'
import { formatApiError } from '@/lib/notificationHelpers'
import { useToast } from '@/lib/toastContext'
import { useTranslations } from 'next-intl'
import { format } from 'date-fns'
import { ru, kk, enUS } from 'date-fns/locale'

interface PaymentRegistryProps {
  locale: string
}

type TabType =
  | 'payments'
  | 'counterparties'
  | 'balance'
  | 'invoices'
  | 'counterparty-details'
  | 'invoice-registry'

const localeMap: Record<string, typeof ru> = {
  ru,
  kz: kk,
  en: enUS,
}

const TAB_VALUES: TabType[] = [
  'payments',
  'counterparties',
  'balance',
  'invoices',
  'counterparty-details',
  'invoice-registry',
]

const STATUS_VALUES: NonNullable<PaymentFilter['status']>[] = [
  'paid',
  'partial',
  'unpaid',
  'overdue',
  'test',
]

function parseTab(value: string | null): TabType | null {
  return value && (TAB_VALUES as string[]).includes(value) ? (value as TabType) : null
}

function parseStatus(value: string | null): PaymentFilter['status'] {
  return value && (STATUS_VALUES as string[]).includes(value)
    ? (value as PaymentFilter['status'])
    : undefined
}

export default function PaymentRegistry({ locale }: PaymentRegistryProps) {
  const toast = useToast()
  const tExport = useTranslations('export')
  const tInvoices = useTranslations('invoices')
  const tFilters = useTranslations('filters')
  const tTabs = useTranslations('tabs')
  const tRegistry = useTranslations('registry')
  const now = new Date()
  const defaultPeriod = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const [payments, setPayments] = useState<Payment[]>([])
  const [analytics, setAnalytics] = useState<PaymentAnalytics | null>(null)
  const [filters, setFilters] = useState<PaymentFilter>({
    period: defaultPeriod,
    page: 1,
    page_size: 10,
  })
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [show1CModal, setShow1CModal] = useState(false)
  const [activeTab, setActiveTab] = useState<TabType>('payments')
  const [selectedCounterparty, setSelectedCounterparty] = useState<Counterparty | null>(null)
  const [tenantContextKey, setTenantContextKey] = useState(0)
  const [portalMode, setPortalMode] = useState(false)
  const [mountedTabs, setMountedTabs] = useState<Set<TabType>>(
    () => new Set<TabType>(['payments']),
  )

  const selectTab = (tab: TabType) => {
    setActiveTab(tab)
    setMountedTabs((prev) => new Set(prev).add(tab))
  }

  const searchParams = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  // Гейт для эффекта записи ниже: реальное состояние React (не ref) — иначе
  // на первом рендере (до того, как гидратация ниже применит значения из
  // URL) эффект записи увидел бы дефолты (activeTab='payments' и т.п.) и
  // затёр бы query, который мы только собираемся прочитать.
  const [hydratedFromUrl, setHydratedFromUrl] = useState(false)

  // Однократная гидратация состояния из URL при монтировании — таб,
  // выбранный контрагент и фильтры реестра, чтобы ссылку можно было
  // переслать коллеге и открыть тот же экран (запрошено пользователем
  // 2026-09-18). Список контрагентов уже грузится целиком на фронте
  // везде (CounterpartiesList/Table) — ищем совпадение по id в нём же,
  // без отдельного backend-эндпоинта "counterparty by id".
  useEffect(() => {
    const tabParam = parseTab(searchParams.get('tab'))
    const cpParam = searchParams.get('cp')
    const periodParam = searchParams.get('period')
    const statusParam = parseStatus(searchParams.get('status'))
    const dateFromParam = searchParams.get('date_from')
    const dateToParam = searchParams.get('date_to')

    if (periodParam || statusParam || dateFromParam || dateToParam) {
      setFilters((prev) => ({
        ...prev,
        ...(periodParam ? { period: periodParam } : {}),
        ...(statusParam ? { status: statusParam } : {}),
        ...(dateFromParam ? { date_from: dateFromParam } : {}),
        ...(dateToParam ? { date_to: dateToParam } : {}),
      }))
    }

    if (cpParam) {
      oneCApi
        .getCounterparties()
        .then((data) => {
          const found = data.counterparties.find((cp) => cp.id === cpParam)
          if (found) {
            setSelectedCounterparty(found)
            selectTab(tabParam === 'balance' ? 'balance' : 'counterparty-details')
          } else if (tabParam) {
            selectTab(tabParam)
          }
        })
        .catch(() => {
          if (tabParam) selectTab(tabParam)
        })
        .finally(() => setHydratedFromUrl(true))
    } else {
      if (tabParam) selectTab(tabParam)
      setHydratedFromUrl(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Пишем текущее состояние обратно в URL после каждого изменения — но
  // только после того, как гидратация выше отработала (см. комментарий у
  // hydratedFromUrl).
  useEffect(() => {
    if (!hydratedFromUrl) return
    const query: Record<string, string> = {}
    if (activeTab !== 'payments') query.tab = activeTab
    if (
      (activeTab === 'counterparty-details' || activeTab === 'balance') &&
      selectedCounterparty?.id
    ) {
      query.cp = selectedCounterparty.id
    }
    if (filters.period) query.period = filters.period
    if (filters.status) query.status = String(filters.status)
    if (filters.date_from) query.date_from = filters.date_from
    if (filters.date_to) query.date_to = filters.date_to

    router.replace({ pathname, query }, { scroll: false })
  }, [
    hydratedFromUrl,
    activeTab,
    selectedCounterparty,
    filters.period,
    filters.status,
    filters.date_from,
    filters.date_to,
    pathname,
    router,
  ])

  useEffect(() => {
    const syncPortal = () => {
      const portal = isPortalSession()
      setPortalMode(portal)
      if (portal) {
        const session = getPortalSession()
        if (session) {
          if (session.role === 'tenant') {
            setFilters((prev) => ({
              ...prev,
              page: 1,
              tenant_name: session.tenant_name || session.legal_name,
              ip_name: session.legal_name,
            }))
          } else {
            setFilters((prev) => ({
              ...prev,
              page: 1,
              ip_name: undefined,
              tenant_name: undefined,
            }))
          }
          setTenantContextKey((k) => k + 1)
        }
      }
    }
    syncPortal()
    window.addEventListener('tenantPortalAuthChanged', syncPortal)
    return () => window.removeEventListener('tenantPortalAuthChanged', syncPortal)
  }, [])

  useEffect(() => {
    const onTenantContextChanged = () => {
      setTenantContextKey((k) => k + 1)
    }
    window.addEventListener('tenantContextChanged', onTenantContextChanged)
    return () => window.removeEventListener('tenantContextChanged', onTenantContextChanged)
  }, [])

  const loadPaymentsTab = useCallback(async () => {
    const requestId = ++loadRequestId.current
    const analyticsFilters = {
      period: filters.period,
      date_from: filters.date_from,
      date_to: filters.date_to,
    }
    const [paymentsResult, analyticsResult] = await Promise.allSettled([
      paymentApi.getPayments(filters),
      paymentApi.getAnalytics(analyticsFilters),
    ])

    if (requestId !== loadRequestId.current) {
      return
    }

    if (paymentsResult.status === 'fulfilled') {
      const paymentsData = paymentsResult.value
      setPayments(paymentsData.items)
      setTotalPages(paymentsData.total_pages)
      setTotal(paymentsData.total)
    }

    if (analyticsResult.status === 'fulfilled') {
      setAnalytics(analyticsResult.value)
    }
  }, [filters])

  const { loading: paymentsTabLoading, refresh: refreshPaymentsTab } = useOneCDataLoad(
    loadPaymentsTab,
    tenantContextKey,
  )

  const refreshPaymentsFrom1C = useCallback(async () => {
    const period = filters.period
    if (!period) {
      toast(tFilters('selectPeriodToast'))
      return
    }
    try {
      const started = await paymentApi.startSyncFrom1C(period)
      if (started.status === 'running') {
        toast(tInvoices('syncRunning'))
        return
      }
      const deadline = Date.now() + 180000
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 2500))
        const st = await paymentApi.getSyncStatus(period)
        if (st.status === 'done') {
          await loadPaymentsTab()
          toast(
            st.records != null
              ? tInvoices('syncFound', { count: st.records, period })
              : tRegistry('syncDone'),
            'success',
          )
          return
        }
        if (st.status === 'failed') {
          toast(tInvoices('syncFailed', { error: st.error || tInvoices('syncUnknownError') }), 'error')
          return
        }
      }
      toast(tInvoices('syncStillRunning'))
    } catch (err) {
      toast(tInvoices('syncStartFailed', { error: formatApiError(err) }), 'error')
    }
  }, [filters.period, loadPaymentsTab, toast, tFilters, tInvoices, tRegistry])

  const filtersSyncRef = useRef(false)
  const loadRequestId = useRef(0)
  useEffect(() => {
    if (!filtersSyncRef.current) {
      filtersSyncRef.current = true
      return
    }
    refreshPaymentsTab()
  }, [
    filters.period,
    filters.date_from,
    filters.date_to,
    filters.ip_name,
    filters.tenant_name,
    filters.status,
    filters.page,
    refreshPaymentsTab,
  ])

  useEffect(() => {
    const handleOpen1CDownload = () => {
      setShow1CModal(true)
    }
    window.addEventListener('open1cDownload', handleOpen1CDownload)
    return () => {
      window.removeEventListener('open1cDownload', handleOpen1CDownload)
    }
  }, [])

  useEffect(() => {
    const handleResetToRegistry = () => {
      setSelectedCounterparty(null)
      setActiveTab('payments')
    }
    window.addEventListener('resetToRegistry', handleResetToRegistry)
    return () => {
      window.removeEventListener('resetToRegistry', handleResetToRegistry)
    }
  }, [])

  const handleFilterChange = (newFilters: Partial<PaymentFilter>) => {
    setFilters((prev) => ({ ...prev, ...newFilters, page: 1 }))
  }

  const handleExport = async () => {
    try {
      const blob = await paymentApi.exportPayments(filters)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `reestr_oplat_${filters.period || 'all'}.xlsx`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Error exporting:', error)
      toast(tExport('error'), 'error')
    }
  }

  const handleCounterpartySelect = (counterparty: Counterparty) => {
    setSelectedCounterparty(counterparty)
    selectTab('counterparty-details')
  }

  const periodLabel = (() => {
    if (filters.date_from && filters.date_to) {
      const from = format(new Date(filters.date_from + 'T12:00:00'), 'd MMMM', {
        locale: localeMap[locale] || ru,
      })
      const to = format(new Date(filters.date_to + 'T12:00:00'), 'd MMMM yyyy', {
        locale: localeMap[locale] || ru,
      })
      return `${from} — ${to}`
    }
    if (filters.period) {
      return tFilters('forPeriod', {
        period: format(new Date(filters.period + '-01'), 'LLLL yyyy', {
          locale: localeMap[locale] || ru,
        }),
      })
    }
    return tFilters('currentPeriod')
  })()

  return (
    <div className="base_layout only_header">
      <Header locale={locale} />

      <section className="main">
        {(activeTab === 'payments' || activeTab === 'invoice-registry') && (
          <section className="filter_header">
            <Filters
              filters={filters}
              onFilterChange={handleFilterChange}
              onExport={handleExport}
              locale={locale}
              onRefreshRegistry={refreshPaymentsFrom1C}
              refreshRegistryLoading={paymentsTabLoading}
            />
          </section>
        )}

        <div className="container no_flex">
          <section className="content_section">
            <div className="column gap-s pv-16">
              {!portalMode && (
                <TenantContextSelector
                  onChange={() => {
                    setTenantContextKey((k) => k + 1)
                  }}
                />
              )}

              <XlsxUploadPanel onImported={loadPaymentsTab} />

              <div className="tabs_header">
                <div
                  className={`tab_item${activeTab === 'payments' ? ' active' : ''}`}
                  onClick={() => selectTab('payments')}
                  role="button"
                  tabIndex={0}
                >
                  <p className="title">{tTabs('registry')}</p>
                </div>
                <div
                  className={`tab_item${activeTab === 'invoice-registry' ? ' active' : ''}`}
                  onClick={() => selectTab('invoice-registry')}
                  role="button"
                  tabIndex={0}
                >
                  <p className="title">{tTabs('invoiceRegistry')}</p>
                </div>
                <div
                  className={`tab_item${activeTab === 'invoices' ? ' active' : ''}`}
                  onClick={() => selectTab('invoices')}
                  role="button"
                  tabIndex={0}
                >
                  <p className="title">{tTabs('invoices')}</p>
                </div>
                <div
                  className={`tab_item${activeTab === 'counterparties' ? ' active' : ''}`}
                  onClick={() => selectTab('counterparties')}
                  role="button"
                  tabIndex={0}
                >
                  <p className="title">{tTabs('counterparties')}</p>
                </div>
                {selectedCounterparty && (
                  <div
                    className={`tab_item${activeTab === 'counterparty-details' ? ' active' : ''}`}
                    onClick={() => selectTab('counterparty-details')}
                    role="button"
                    tabIndex={0}
                  >
                    <p className="title">{selectedCounterparty.fullName}</p>
                  </div>
                )}
              </div>

              {mountedTabs.has('payments') && (
                <div className={activeTab === 'payments' ? 'column gap-s' : 'hidden'}>
                  {((filters.ip_name && filters.ip_name.toLowerCase() === 'тест') ||
                    (filters.tenant_name && filters.tenant_name.toLowerCase() === 'тест') ||
                    (filters.status && filters.status.toString().toLowerCase() === 'test')) && (
                    <div className="card">
                      <p className="title">{tTabs('testMode')}</p>
                    </div>
                  )}

                  {analytics && (
                    <AnalyticsCards
                      analytics={analytics}
                      activeStatus={filters.status as 'paid' | 'partial' | 'unpaid' | 'overdue' | undefined}
                      onSelectStatus={(status) => handleFilterChange({ status })}
                    />
                  )}

                  <CatalogTenantsList />

                  <CounterpartiesTable
                    onSelect={handleCounterpartySelect}
                    locale={locale}
                    cacheResetKey={tenantContextKey}
                    paymentStatusFilter={filters.status}
                    periodLabel={periodLabel}
                    period={filters.period}
                    dateFrom={filters.date_from}
                    dateTo={filters.date_to}
                    unpaidInvoiceCount={
                      analytics
                        ? (analytics.unpaid || 0) + (analytics.overdue || 0)
                        : undefined
                    }
                  />
                </div>
              )}

              {mountedTabs.has('invoice-registry') && (
                <div className={activeTab === 'invoice-registry' ? '' : 'hidden'}>
                  <InvoiceRegistryTable
                    locale={locale}
                    cacheResetKey={tenantContextKey}
                    period={filters.period}
                    dateFrom={filters.date_from}
                    dateTo={filters.date_to}
                    periodLabel={periodLabel}
                  />
                </div>
              )}

              {mountedTabs.has('invoices') && (
                <div className={activeTab === 'invoices' ? '' : 'hidden'}>
                  <InvoicesList period={filters.period} cacheResetKey={tenantContextKey} />
                </div>
              )}

              {mountedTabs.has('counterparties') && (
                <div className={activeTab === 'counterparties' ? '' : 'hidden'}>
                  <CounterpartiesList
                    onSelect={handleCounterpartySelect}
                    cacheResetKey={tenantContextKey}
                  />
                </div>
              )}

              {mountedTabs.has('counterparty-details') && selectedCounterparty && (
                <div className={activeTab === 'counterparty-details' ? '' : 'hidden'}>
                  <CounterpartyDetails
                    counterparty={selectedCounterparty}
                    onClose={() => {
                      setSelectedCounterparty(null)
                      selectTab('counterparties')
                    }}
                  />
                </div>
              )}

              {mountedTabs.has('balance') && selectedCounterparty && (
                <div className={activeTab === 'balance' ? '' : 'hidden'}>
                  <CounterpartyBalance
                    counterpartyId={selectedCounterparty.id}
                    counterpartyName={selectedCounterparty.fullName}
                    onClose={() => {
                      setSelectedCounterparty(null)
                      selectTab('counterparties')
                    }}
                  />
                </div>
              )}
            </div>
          </section>
        </div>
      </section>

      <OneCDownloadModal
        isOpen={show1CModal}
        onClose={() => setShow1CModal(false)}
        period={filters.period}
      />
    </div>
  )
}
