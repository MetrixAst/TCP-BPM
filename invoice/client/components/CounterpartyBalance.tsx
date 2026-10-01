'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { oneCApi, Balance } from '@/lib/api'

interface CounterpartyBalanceProps {
  counterpartyId: string
  counterpartyName?: string
  onClose?: () => void
}

export default function CounterpartyBalance({ counterpartyId, counterpartyName, onClose }: CounterpartyBalanceProps) {
  const t = useTranslations('counterpartyBalance')
  const [balance, setBalance] = useState<Balance | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [since, setSince] = useState('')

  const loadBalance = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await oneCApi.getBalance(counterpartyId, since || undefined)
      if (response.error) {
        setError(response.error)
      } else {
        setBalance(response)
      }
    } catch (err: any) {
      setError(err.message || t('loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  const handleLoad = () => {
    loadBalance()
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">
          {t('title')}
          {counterpartyName && <span className="text-gray-600 ml-2">({counterpartyName})</span>}
        </h2>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700"
          >
            ✕
          </button>
        )}
      </div>

      <div className="mb-4 flex gap-2">
        <input
          type="datetime-local"
          value={since}
          onChange={(e) => setSince(e.target.value)}
          placeholder={t('datePlaceholder')}
          className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <button
          onClick={handleLoad}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
        >
          {loading ? t('loading') : t('loadButton')}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">
          {error}
        </div>
      )}

      {loading && !balance ? (
        <div className="text-center py-8">{t('loadingBalance')}</div>
      ) : balance ? (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-blue-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">{t('receivable')}</div>
              <div className="text-2xl font-bold text-blue-600">
                {balance.balances.receivable.toLocaleString('ru-RU')} ₸
              </div>
            </div>
            <div className="bg-red-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">{t('payable')}</div>
              <div className="text-2xl font-bold text-red-600">
                {balance.balances.payable.toLocaleString('ru-RU')} ₸
              </div>
            </div>
            <div className="bg-green-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">{t('net')}</div>
              <div className="text-2xl font-bold text-green-600">
                {balance.balances.net.toLocaleString('ru-RU')} ₸
              </div>
            </div>
          </div>

          {balance.aging && balance.aging.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold mb-2">{t('agingTitle')}</h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t('period')}</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t('amount')}</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {balance.aging.map((item, index) => (
                      <tr key={index}>
                        <td className="px-4 py-3 text-sm text-gray-900">{item.period}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">
                          {item.amount.toLocaleString('ru-RU')} ₸
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {(balance.by_documents && balance.by_documents.length > 0) || (balance.documents && balance.documents.length > 0) ? (
            <div>
              <h3 className="text-lg font-semibold mb-2">{t('documentsTitle')}</h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t('columns.type')}</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t('columns.document')}</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t('columns.date')}</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t('columns.amount')}</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t('columns.paid')}</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t('columns.debt')}</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {(balance.by_documents || balance.documents || []).map((doc: any, index: number) => (
                      <tr key={index}>
                        <td className="px-4 py-3 text-sm text-gray-900">{doc.type || '-'}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{doc.document || doc.number || '-'}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{doc.date || '-'}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">
                          {doc.amount !== undefined ? `${doc.amount.toLocaleString('ru-RU')} ₸` : '-'}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-900">
                          {doc.paid !== undefined ? `${doc.paid.toLocaleString('ru-RU')} ₸` : '-'}
                        </td>
                        <td className={`px-4 py-3 text-sm font-medium ${
                          doc.debt !== undefined && doc.debt < 0 ? 'text-red-600' : 
                          doc.debt !== undefined && doc.debt > 0 ? 'text-green-600' : 
                          'text-gray-900'
                        }`}>
                          {doc.debt !== undefined ? `${doc.debt.toLocaleString('ru-RU')} ₸` : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="text-center py-8 text-gray-500">
          {t('emptyHint')}
        </div>
      )}
    </div>
  )
}
