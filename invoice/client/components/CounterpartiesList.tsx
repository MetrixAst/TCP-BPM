'use client'

import { useState, useCallback, useRef } from 'react'
import { useTranslations } from 'next-intl'
import { oneCApi, Counterparty, CounterpartyFolder } from '@/lib/api'
import { setPaymentTypesEnabled } from '@/lib/paymentTypesContext'
import { getEffectiveTenantId } from '@/lib/tenantContext'
import { useOneCDataLoad } from '@/lib/useOneCDataLoad'
import TabRefreshButton from './TabRefreshButton'
import CounterpartyFolderTabs from './CounterpartyFolderTabs'
import { waitForCounterpartySync } from '@/lib/pollCounterpartySync'

interface CounterpartiesListProps {
  limit?: number
  onSelect?: (counterparty: Counterparty) => void
  cacheResetKey?: number
}

export default function CounterpartiesList({
  limit = 10000,
  onSelect,
  cacheResetKey,
}: CounterpartiesListProps) {
  const t = useTranslations('counterparties')
  const tRegistry = useTranslations('registry')
  const [counterparties, setCounterparties] = useState<Counterparty[]>([])
  const [folders, setFolders] = useState<CounterpartyFolder[]>([])
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [syncing, setSyncing] = useState(false)

  const includeInvoiceStatusRef = useRef(false)

  const loadData = useCallback(async () => {
    const withInvoiceStatus = includeInvoiceStatusRef.current
    includeInvoiceStatusRef.current = false
    if (!getEffectiveTenantId()) {
      setError(t('selectTenantHint'))
      setCounterparties([])
      setFolders([])
      return
    }
    setError(null)
    try {
      const response = await oneCApi.getCounterparties(limit, {
        include_invoice_status: withInvoiceStatus,
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
          setFolders(
            Array.from(seen.values()).sort((a, b) => a.fullName.localeCompare(b.fullName, 'ru')),
          )
        }
        if (response.sync_error) {
          setError(response.sync_error)
        }
      } else if (response.error) {
        setError(response.error)
      }
    } catch {
      // ignore load errors
    }
  }, [limit])

  const { loading, refresh } = useOneCDataLoad(loadData, cacheResetKey)

  const refreshFrom1C = useCallback(async () => {
    if (!getEffectiveTenantId()) return
    includeInvoiceStatusRef.current = true
    setSyncing(true)
    setError(null)
    try {
      const sync = await oneCApi.syncCounterparties()
      if (!sync.ok) {
        setError(sync.error || tRegistry('counterpartiesSyncFailed'))
        return
      }
      const result = await waitForCounterpartySync({
        limit,
        includeInvoiceStatus: true,
      })
      if (result.sync_error) {
        setError(result.sync_error)
      }
      refresh()
    } catch {
      setError(tRegistry('syncContactServerFailed'))
    } finally {
      setSyncing(false)
    }
  }, [limit, refresh, tRegistry])

  const filteredCounterparties = counterparties.filter((cp) => {
    if (selectedFolder) {
      const folder = (cp.folderName || '').trim()
      if (folder.toLowerCase() !== selectedFolder.toLowerCase()) return false
    }
    return (
      cp.fullName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      cp.bin?.includes(searchTerm) ||
      cp.iin?.includes(searchTerm)
    )
  })

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">{t('title')}</h2>
        <TabRefreshButton onClick={refreshFrom1C} loading={syncing || loading} />
      </div>

      <CounterpartyFolderTabs
        folders={folders}
        selected={selectedFolder}
        onSelect={setSelectedFolder}
      />

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">
          {error}
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

      {loading && counterparties.length === 0 ? (
        <div className="text-center py-8">{t('loading')}</div>
      ) : filteredCounterparties.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          {searchTerm || selectedFolder ? t('notFound') : t('empty')}
        </div>
      ) : (
        <div className="overflow-x-auto w-full">
          <table className="min-w-[1000px] w-full table-auto divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">{t('columns.name')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">{t('columns.bin')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">{t('columns.iin')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">{t('columns.phone')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">{t('columns.email')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">{t('columns.invoices')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">{t('columns.contracts')}</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredCounterparties.map((counterparty) => (
                <tr
                  key={counterparty.id}
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => onSelect?.(counterparty)}
                >
                  <td
                    className="px-4 py-3 text-sm font-medium text-gray-900 min-w-[260px] max-w-[480px] whitespace-normal break-words"
                    title={counterparty.fullName}
                  >
                    {counterparty.fullName}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">{counterparty.bin || '—'}</td>
                  <td className="px-4 py-3 text-sm text-gray-900">{counterparty.iin || '—'}</td>
                  <td className="px-4 py-3 text-sm text-gray-900">{counterparty.phoneNumber || counterparty.phone || '—'}</td>
                  <td className="px-4 py-3 text-sm text-gray-900">{counterparty.email || '—'}</td>
                  <td className="px-4 py-3 text-sm text-gray-900">
                    {counterparty.invoiceCount ?? 0}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">{counterparty.contracts?.length ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 text-sm text-gray-500">
        {t('total', { shown: filteredCounterparties.length, total: counterparties.length })}
      </div>
    </div>
  )
}
