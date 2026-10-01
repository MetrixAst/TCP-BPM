'use client'

import { FormEvent, useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from '@/i18n/routing'
import { isPortalSession } from '@/lib/tenantContext'
import MetriXBrandLogo from '@/components/MetriXBrandLogo'
import { tenantAuthApi } from '@/lib/api'
import { setPortalAuth, refreshPortalSession } from '@/lib/tenantAuth'
import {
  notifyTenantContextChanged,
  setSelectedTenantId,
  setSelectedTrcId,
} from '@/lib/tenantContext'

export default function TenantLoginPage() {
  const t = useTranslations('login')
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isPortalSession()) {
      router.replace('/')
    }
  }, [router])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await tenantAuthApi.login(username.trim(), password)
      const role = data.role || (data.tenant_id ? 'tenant' : 'trc')
      setPortalAuth(data.access_token, {
        role,
        tenant_id: data.tenant_id,
        trc_id: data.trc_id,
        tenant_name: data.tenant_name,
        trc_name: data.trc_name,
        legal_name: data.legal_name,
      })
      setSelectedTrcId(data.trc_id)
      setSelectedTenantId(role === 'tenant' ? data.tenant_id : null)
      notifyTenantContextChanged()
      if (role === 'tenant') {
        await refreshPortalSession()
      }
      router.push('/')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number } }
      if (axiosErr.response?.status === 401) {
        setError(t('invalidCredentials'))
      } else {
        setError(t('connectionError'))
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-md border border-gray-200 p-8">
        <div className="flex justify-center mb-6">
          <MetriXBrandLogo />
        </div>
        <h1 className="text-xl font-semibold text-center text-gray-900 mb-2">
          {t('title')}
        </h1>
        <p className="text-sm text-center text-gray-500 mb-6">
          {t('subtitle')}
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('loginLabel')}</label>
            <input
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('passwordLabel')}</label>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-60"
          >
            {loading ? t('submitting') : t('submit')}
          </button>
        </form>
      </div>
    </div>
  )
}
