'use client'

import { useState, useEffect } from 'react'
import { PaymentFilter } from '@/lib/api'
import { paymentApi } from '@/lib/api'
import { catalogApi, CatalogTenant } from '@/lib/catalogApi'
import {
  getEffectiveTrcId,
  getSelectedTenantId,
  notifyTenantContextChanged,
  setSelectedTenantId,
} from '@/lib/tenantContext'
import { getPortalSession, isTenantPortalSession, isTrcPortalSession } from '@/lib/tenantAuth'
import { useTranslations } from 'next-intl'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import { format, type Locale } from 'date-fns'
import { ru, kk, enUS } from 'date-fns/locale'
import MaskedIcon from './MaskedIcon'
import { metrixIcon } from '@/lib/metrixAssets'
import { useToggleDropdown } from '@/hooks/useToggleDropdown'
import TabRefreshButton from './TabRefreshButton'

interface FiltersProps {
  filters: PaymentFilter
  onFilterChange: (filters: Partial<PaymentFilter>) => void
  onExport: () => void
  locale: string
  onRefreshRegistry?: () => void
  refreshRegistryLoading?: boolean
}

const localeMap: Record<string, Locale> = {
  ru: ru,
  kz: kk,
  en: enUS,
}

export default function Filters({
  filters,
  onFilterChange,
  onExport,
  locale,
  onRefreshRegistry,
  refreshRegistryLoading,
}: FiltersProps) {
  const t = useTranslations('filters')
  const tCommon = useTranslations('common')
  const [tenantOptions, setTenantOptions] = useState<string[]>([])
  const [catalogTenants, setCatalogTenants] = useState<CatalogTenant[]>([])
  const tenantLocked = isTenantPortalSession()
  const usesCatalogTenants = isTrcPortalSession() || Boolean(getEffectiveTrcId())
  const [periodMode, setPeriodMode] = useState<'month' | 'range'>(
    filters.date_from && filters.date_to ? 'range' : 'month',
  )
  const [selectedDate, setSelectedDate] = useState<Date | null>(
    filters.period ? new Date(filters.period + '-01') : null,
  )
  const [rangeStart, setRangeStart] = useState<Date | null>(
    filters.date_from ? new Date(filters.date_from + 'T12:00:00') : null,
  )
  const [rangeEnd, setRangeEnd] = useState<Date | null>(
    filters.date_to ? new Date(filters.date_to + 'T12:00:00') : null,
  )
  const { toggle, isOpen, close } = useToggleDropdown()

  useEffect(() => {
    if (filters.date_from && filters.date_to) {
      setPeriodMode('range')
      setRangeStart(new Date(filters.date_from + 'T12:00:00'))
      setRangeEnd(new Date(filters.date_to + 'T12:00:00'))
    } else if (filters.period) {
      setSelectedDate(new Date(filters.period + '-01'))
    }
  }, [filters.period, filters.date_from, filters.date_to])

  useEffect(() => {
    const loadOptions = async () => {
      try {
        const session = getPortalSession()
        if (session?.role === 'tenant') {
          setCatalogTenants([])
          setTenantOptions([session.tenant_name || session.legal_name])
          return
        }
        const trcId = getEffectiveTrcId()
        if (trcId) {
          const tenants = await catalogApi.listTenants(trcId)
          setCatalogTenants(tenants)
          const names = tenants.map((tenant) => tenant.name)
          setTenantOptions([tCommon('all'), ...Array.from(new Set(names))])
          return
        }
        setCatalogTenants([])
        const data = await paymentApi.getPayments({ page_size: 1000 })
        const uniqueTenants = Array.from(new Set(data.items.map((p) => p.tenant_name)))
        setTenantOptions([tCommon('all'), ...uniqueTenants])
      } catch (error) {
        console.error('Error loading options:', error)
      }
    }
    loadOptions()
    window.addEventListener('tenantContextChanged', loadOptions)
    window.addEventListener('tenantPortalAuthChanged', loadOptions)
    return () => {
      window.removeEventListener('tenantContextChanged', loadOptions)
      window.removeEventListener('tenantPortalAuthChanged', loadOptions)
    }
  }, [tCommon])

  const handlePeriodChange = (date: Date | null) => {
    setSelectedDate(date)
    if (date) {
      const period = format(date, 'yyyy-MM')
      onFilterChange({ period, date_from: undefined, date_to: undefined, page: 1 })
    } else {
      onFilterChange({ period: undefined, date_from: undefined, date_to: undefined, page: 1 })
    }
  }

  const handleRangeChange = (dates: [Date | null, Date | null]) => {
    const [start, end] = dates
    setRangeStart(start)
    setRangeEnd(end)
    if (start && end) {
      const from = start <= end ? start : end
      const to = start <= end ? end : start
      onFilterChange({
        date_from: format(from, 'yyyy-MM-dd'),
        date_to: format(to, 'yyyy-MM-dd'),
        period: format(from, 'yyyy-MM'),
        page: 1,
      })
      return
    }
  }

  const switchPeriodMode = (mode: 'month' | 'range') => {
    setPeriodMode(mode)
    if (mode === 'month') {
      setRangeStart(null)
      setRangeEnd(null)
      if (selectedDate) {
        onFilterChange({
          period: format(selectedDate, 'yyyy-MM'),
          date_from: undefined,
          date_to: undefined,
          page: 1,
        })
      } else {
        onFilterChange({ date_from: undefined, date_to: undefined, page: 1 })
      }
    } else {
      setRangeStart(null)
      setRangeEnd(null)
    }
  }

  const currentLocale = localeMap[locale] || ru
  const allLabel = tCommon('all')
  const selectedCatalogTenant =
    usesCatalogTenants && catalogTenants.length > 0
      ? catalogTenants.find((tenant) => tenant.id === getSelectedTenantId()) ?? null
      : null
  const tenantLabel = usesCatalogTenants
    ? selectedCatalogTenant?.name || allLabel
    : filters.tenant_name || allLabel
  const statusLabel = filters.status
    ? t(`status.${filters.status}` as 'status.paid')
    : allLabel

  const periodDisplay =
    periodMode === 'range' && rangeStart && rangeEnd
      ? `${format(rangeStart, 'd MMMM', { locale: currentLocale })} — ${format(rangeEnd, 'd MMMM yyyy', { locale: currentLocale })}`
      : periodMode === 'range' && rangeStart
        ? `${t('rangeFrom')} ${format(rangeStart, 'd MMMM yyyy', { locale: currentLocale })}`
        : periodMode === 'range'
          ? t('selectPeriod')
          : selectedDate
          ? format(selectedDate, 'LLLL yyyy', { locale: currentLocale })
          : t('selectPeriod')

  const selectTenant = (value: string | undefined) => {
    if (tenantLocked) return
    if (usesCatalogTenants && catalogTenants.length > 0) {
      if (value) {
        const tenant = catalogTenants.find((item) => item.name === value)
        setSelectedTenantId(tenant?.id ?? null)
        // Контекст арендатора каталога — через tenant_id; tenant_name в API = фильтр по контрагенту.
        onFilterChange({ tenant_name: undefined, ip_name: undefined })
      } else {
        setSelectedTenantId(null)
        onFilterChange({ tenant_name: undefined, ip_name: undefined })
      }
      notifyTenantContextChanged()
    } else {
      onFilterChange({ tenant_name: value })
    }
    close()
  }

  const selectStatus = (value: PaymentFilter['status']) => {
    onFilterChange({ status: value })
    close()
  }

  return (
    <div className="container">
      <div className="block">
        <div className="togglers single mw">
          <div
            className={`toggler_item toggle_handler${isOpen('filter_period') ? ' opened' : ''}`}
            onClick={toggle('filter_period')}
          >
            <p className="block_title">{t('period')}</p>
            {periodDisplay}
            <div
              className={`toggle_content auto_dismiss period-picker-dropdown${isOpen('filter_period') ? ' is-open' : ''}`}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="period-picker-modes">
                <button
                  type="button"
                  className={`period-picker-mode${periodMode === 'month' ? ' is-active' : ''}`}
                  onClick={() => switchPeriodMode('month')}
                >
                  {t('periodModeMonth')}
                </button>
                <button
                  type="button"
                  className={`period-picker-mode${periodMode === 'range' ? ' is-active' : ''}`}
                  onClick={() => switchPeriodMode('range')}
                >
                  {t('periodModeRange')}
                </button>
              </div>
              {periodMode === 'month' ? (
                <DatePicker
                  selected={selectedDate}
                  onChange={handlePeriodChange}
                  dateFormat="MMMM yyyy"
                  showMonthYearPicker
                  inline
                  locale={currentLocale}
                  calendarClassName="period-picker-calendar"
                />
              ) : (
                <>
                  <p className="period-picker-hint">
                    {rangeStart && !rangeEnd ? t('rangePickTo') : t('rangeHint')}
                  </p>
                  <DatePicker
                    selectsRange
                    startDate={rangeStart}
                    endDate={rangeEnd}
                    onChange={handleRangeChange}
                    inline
                    locale={currentLocale}
                    calendarClassName="period-picker-calendar"
                  />
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="block">
        <div className="togglers single mw">
          <div
            className={`toggler_item toggle_handler${isOpen('filter_tenants') ? ' opened' : ''}`}
            onClick={toggle('filter_tenants')}
          >
            <p className="block_title">{t('tenants')}</p>
            {tenantLabel}
            <div
              className={`toggle_content auto_dismiss${isOpen('filter_tenants') ? ' is-open' : ''}`}
              onClick={(e) => e.stopPropagation()}
            >
              <p className="section_title">{t('tenants')}</p>
              {!tenantLocked && (
                <div className="info_item select_item" onClick={() => selectTenant(undefined)}>
                  <div className="values">
                    <p className="value">{allLabel}</p>
                  </div>
                </div>
              )}
              {tenantOptions
                .filter((tenant) => tenant !== allLabel)
                .map((tenant) => (
                  <div
                    key={tenant}
                    className="info_item select_item"
                    onClick={() => selectTenant(tenant)}
                  >
                    <div className="values">
                      <p className="value">{tenant}</p>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      </div>

      <div className="block">
        <div className="togglers single mw">
          <div
            className={`toggler_item toggle_handler${isOpen('filter_status') ? ' opened' : ''}`}
            onClick={toggle('filter_status')}
          >
            <p className="block_title">{t('paymentStatus')}</p>
            {statusLabel}
            <div
              className={`toggle_content auto_dismiss${isOpen('filter_status') ? ' is-open' : ''}`}
              onClick={(e) => e.stopPropagation()}
            >
              <p className="section_title">{t('paymentStatus')}</p>
              <div className="info_item select_item" onClick={() => selectStatus(undefined)}>
                <div className="values">
                  <p className="value">{allLabel}</p>
                </div>
              </div>
              <div className="info_item select_item" onClick={() => selectStatus('paid')}>
                <div className="values">
                  <p className="value">{t('status.paid')}</p>
                </div>
              </div>
              <div className="info_item select_item" onClick={() => selectStatus('partial')}>
                <div className="values">
                  <p className="value">{t('status.partial')}</p>
                </div>
              </div>
              <div className="info_item select_item" onClick={() => selectStatus('unpaid')}>
                <div className="values">
                  <p className="value">{t('status.unpaid')}</p>
                </div>
              </div>
              <div className="info_item select_item" onClick={() => selectStatus('overdue')}>
                <div className="values">
                  <p className="value">{t('status.overdue')}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="block flex">
        <button
          type="button"
          className="button size-m"
          onClick={() => {
            onFilterChange({ page: 1 })
          }}
        >
          {tCommon('apply')}
        </button>
        <button
          type="button"
          className="button size-m color-gray"
          onClick={() => {
            const event = new CustomEvent('open1cDownload')
            window.dispatchEvent(event)
          }}
        >
          {t('downloadFrom1c')}
        </button>
        {onRefreshRegistry && (
          <TabRefreshButton
            onClick={onRefreshRegistry}
            loading={refreshRegistryLoading}
            label={t('refreshRegistry')}
          />
        )}
      </div>

      <div className="block">
        <p className="block_title">{t('exportLabel')}</p>
        <div className="row gap-4">
          <button type="button" className="button size-m color-gray" onClick={onExport}>
            <MaskedIcon icon={metrixIcon('file-chart-column.svg')} />
            Excel
          </button>
        </div>
      </div>
    </div>
  )
}
