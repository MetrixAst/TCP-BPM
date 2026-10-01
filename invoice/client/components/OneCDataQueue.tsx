'use client'

import { useState, useCallback } from 'react'
import { oneCApi, DataRecord, ConfirmRequest } from '@/lib/api'
import { getEffectiveTenantId } from '@/lib/tenantContext'
import { useOneCDataLoad } from '@/lib/useOneCDataLoad'
import { useToast } from '@/lib/toastContext'
import TabRefreshButton from './TabRefreshButton'

interface OneCDataQueueProps {
  limit?: number
  cacheResetKey?: number
}

export default function OneCDataQueue({ limit = 100, cacheResetKey }: OneCDataQueueProps) {
  const toast = useToast()
  const [data, setData] = useState<DataRecord[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [syncToken, setSyncToken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [confirming, setConfirming] = useState(false)

  const loadData = useCallback(async () => {
    if (!getEffectiveTenantId()) {
      setError('Выберите арендатора в блоке выше')
      setData([])
      return
    }
    setError(null)
    try {
      const response = await oneCApi.getData(limit)
      if (response.error) {
        setError(response.error)
      } else {
        setData(response.data)
        setHasMore(response.has_more)
        setSyncToken(response.sync_token)
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Ошибка загрузки данных'
      setError(message)
    }
  }, [limit])

  const { loading, refresh } = useOneCDataLoad(loadData, cacheResetKey)

  const handleSelect = (id: string) => {
    const newSelected = new Set(selectedIds)
    if (newSelected.has(id)) {
      newSelected.delete(id)
    } else {
      newSelected.add(id)
    }
    setSelectedIds(newSelected)
  }

  const handleSelectAll = () => {
    if (selectedIds.size === data.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(data.map(item => item.id)))
    }
  }

  const handleConfirm = async () => {
    if (selectedIds.size === 0 || !syncToken) {
      toast('Выберите записи для подтверждения')
      return
    }

    setConfirming(true)
    try {
      const request: ConfirmRequest = {
        received_ids: Array.from(selectedIds),
        status: 'sent',
        sync_token: syncToken
      }
      const response = await oneCApi.confirm(request)
      if (response.error) {
        toast(`Ошибка подтверждения: ${response.error}`, 'error')
      } else {
        toast(`Подтверждено: ${response.confirmed}, Ошибок: ${response.failed}`, 'success')
        setSelectedIds(new Set())
        refresh()
      }
    } catch (err: any) {
      toast(`Ошибка подтверждения: ${err.message}`, 'error')
    } finally {
      setConfirming(false)
    }
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">Данные из очереди 1С</h2>
        <div className="flex gap-2">
          <TabRefreshButton onClick={refresh} loading={loading} />
          {syncToken && (
            <button
              onClick={handleConfirm}
              disabled={confirming || selectedIds.size === 0}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400"
            >
              {confirming ? 'Подтверждение...' : `Подтвердить (${selectedIds.size})`}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">
          {error}
        </div>
      )}

      {loading && data.length === 0 ? (
        <div className="text-center py-8">Загрузка данных...</div>
      ) : data.length === 0 ? (
        <div className="text-center py-8 text-gray-500">Нет данных</div>
      ) : (
        <>
          <div className="mb-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={selectedIds.size === data.length && data.length > 0}
                onChange={handleSelectAll}
                className="w-4 h-4"
              />
              <span>Выбрать все ({data.length})</span>
            </label>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Выбрать</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Тип</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Данные</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {data.map((record) => (
                  <tr key={record.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(record.id)}
                        onChange={() => handleSelect(record.id)}
                        className="w-4 h-4"
                      />
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">{record.id}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{record.type}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      <pre className="text-xs bg-gray-100 p-2 rounded max-w-md overflow-auto">
                        {JSON.stringify(record.data, null, 2)}
                      </pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {hasMore && (
            <div className="mt-4 text-sm text-gray-500">
              Есть еще данные. Увеличьте лимит для загрузки больше записей.
            </div>
          )}
        </>
      )}
    </div>
  )
}
