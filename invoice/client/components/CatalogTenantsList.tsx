'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { catalogApi, CatalogTenant } from '@/lib/catalogApi'
import { getEffectiveTrcId, isPortalSession } from '@/lib/tenantContext'

export default function CatalogTenantsList() {
  const t = useTranslations('catalogTenants')
  const [tenants, setTenants] = useState<CatalogTenant[]>([])
  const [trcName, setTrcName] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const trcId = getEffectiveTrcId()
      if (!trcId) {
        setTenants([])
        return
      }
      const [trcs, list] = await Promise.all([
        catalogApi.listTrcs(),
        catalogApi.listTenants(trcId),
      ])
      setTrcName(trcs.find((t) => t.id === trcId)?.name || '')
      setTenants(list)
    } catch (e) {
      console.error(e)
      setTenants([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const onContext = () => load()
    window.addEventListener('tenantContextChanged', onContext)
    return () => window.removeEventListener('tenantContextChanged', onContext)
  }, [])

  if (isPortalSession()) {
    return null
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm p-4 mb-4 text-sm text-gray-500">
        {t('loading')}
      </div>
    )
  }

  if (tenants.length === 0) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4 text-sm text-amber-900">
        {t('empty', { trc: trcName || '—' })}
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow-sm p-4 mb-4">
      <h3 className="text-sm font-semibold text-gray-800 mb-3">
        {t('heading', { trc: trcName, count: tenants.length })}
      </h3>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="py-2 pr-4">{t('columns.name')}</th>
              <th className="py-2 pr-4">{t('columns.orgType')}</th>
              <th className="py-2 pr-4">{t('columns.binIin')}</th>
              <th className="py-2">{t('columns.phone')}</th>
            </tr>
          </thead>
          <tbody>
            {tenants.map((t) => (
              <tr key={t.id} className="border-b border-gray-100">
                <td className="py-2 pr-4 font-medium">{t.name}</td>
                <td className="py-2 pr-4">
                  {t.org_type}: {t.legal_name}
                </td>
                <td className="py-2 pr-4">
                  {t.bin_value || '—'} / {t.iin_value || '—'}
                </td>
                <td className="py-2">{t.phone || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
