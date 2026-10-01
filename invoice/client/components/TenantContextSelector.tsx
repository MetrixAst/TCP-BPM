'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { catalogApi, CatalogTenant, CatalogTRC } from '@/lib/catalogApi'
import {
  getSelectedTenantId,
  getSelectedTrcId,
  notifyTenantContextChanged,
  setSelectedTenantId,
  setSelectedTrcId,
} from '@/lib/tenantContext'

interface TenantContextSelectorProps {
  onChange?: (trcId: number | null, tenantId: number | null, tenant: CatalogTenant | null) => void
}

export default function TenantContextSelector({ onChange }: TenantContextSelectorProps) {
  const t = useTranslations('tenantContext')
  const [trcs, setTrcs] = useState<CatalogTRC[]>([])
  const [tenants, setTenants] = useState<CatalogTenant[]>([])
  const [trcId, setTrcId] = useState<number | null>(getSelectedTrcId())
  const [tenantId, setTenantId] = useState<number | null>(getSelectedTenantId())

  useEffect(() => {
    const syncTrcs = () => {
      catalogApi.listTrcs().then((data) => {
        setTrcs(data)
        const saved = getSelectedTrcId()
        const initial = saved && data.some((t) => t.id === saved) ? saved : data[0]?.id ?? null
        setTrcId(initial)
        if (initial) setSelectedTrcId(initial)
      })
    }
    syncTrcs()
    window.addEventListener('tenantContextChanged', syncTrcs)
    return () => window.removeEventListener('tenantContextChanged', syncTrcs)
  }, [])

  useEffect(() => {
    if (!trcId) {
      setTenants([])
      return
    }
    catalogApi.listTenants(trcId).then((data) => {
      setTenants(data)
      const saved = getSelectedTenantId()
      const initial =
        saved && data.some((t) => t.id === saved) ? saved : data[0]?.id ?? null
      setTenantId(initial)
      if (initial) setSelectedTenantId(initial)
      else setSelectedTenantId(null)
      const tenant = data.find((t) => t.id === initial) ?? null
      onChange?.(trcId, initial, tenant)
      notifyTenantContextChanged()
    })
  }, [trcId])

  useEffect(() => {
    const tenant = tenants.find((t) => t.id === tenantId) ?? null
    onChange?.(trcId, tenantId, tenant)
  }, [tenantId, tenants, trcId])

  if (trcs.length === 0) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 text-sm text-amber-900">
        {t('notConfigured')}
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow-sm p-4 mb-4 flex flex-wrap gap-4 items-end">
      <div className="flex flex-col">
        <label className="text-sm font-medium text-gray-700 mb-1">{t('trcLabel')}</label>
        <select
          value={trcId ?? ''}
          onChange={(e) => {
            const id = Number(e.target.value)
            setTrcId(id)
            setSelectedTrcId(id)
            setTenantId(null)
            setSelectedTenantId(null)
            notifyTenantContextChanged()
          }}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm min-w-[200px]"
        >
          {trcs.map((trc) => (
            <option key={trc.id} value={trc.id}>
              {trc.name}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col">
        <label className="text-sm font-medium text-gray-700 mb-1">{t('tenantLabel')}</label>
        <select
          value={tenantId ?? ''}
          onChange={(e) => {
            const id = Number(e.target.value)
            setTenantId(id)
            setSelectedTenantId(id)
            notifyTenantContextChanged()
          }}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm min-w-[240px]"
          disabled={tenants.length === 0}
        >
          {tenants.length === 0 && <option value="">{t('noTenants')}</option>}
          {tenants.map((tenant) => (
            <option key={tenant.id} value={tenant.id}>
              {tenant.name} ({tenant.org_type}: {tenant.legal_name})
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
