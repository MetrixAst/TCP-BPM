const TOKEN_KEY = 'tenant_portal_token'
const SESSION_KEY = 'tenant_portal_session'

export type PortalRole = 'tenant' | 'trc'

export interface TenantPortalSession {
  role: PortalRole
  tenant_id: number | null
  trc_id: number
  tenant_name: string
  trc_name: string
  legal_name: string
}

export function getPortalToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function getPortalSession(): TenantPortalSession | null {
  if (typeof window === 'undefined') return null
  const raw = localStorage.getItem(SESSION_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as TenantPortalSession
    if (!parsed.role) {
      parsed.role = parsed.tenant_id ? 'tenant' : 'trc'
    }
    return parsed
  } catch {
    return null
  }
}

export function isPortalSession(): boolean {
  return Boolean(getPortalToken() && getPortalSession())
}

export function isTenantPortalSession(): boolean {
  const session = getPortalSession()
  return Boolean(session && session.role === 'tenant')
}

export function isTrcPortalSession(): boolean {
  const session = getPortalSession()
  return Boolean(session && session.role === 'trc')
}

export async function refreshPortalSession(): Promise<TenantPortalSession | null> {
  const token = getPortalToken()
  const current = getPortalSession()
  if (!token || !current) return null
  try {
    const { tenantAuthApi } = await import('./api')
    const data = await tenantAuthApi.me()
    const session: TenantPortalSession = {
      role: data.role || current.role,
      tenant_id: data.tenant_id ?? current.tenant_id,
      trc_id: data.trc_id,
      tenant_name: data.tenant_name || current.tenant_name,
      trc_name: data.trc_name || current.trc_name,
      legal_name: data.legal_name || current.legal_name,
    }
    if (data.payment_types_enabled) {
      const { setPaymentTypesEnabled } = await import('./paymentTypesContext')
      setPaymentTypesEnabled(data.payment_types_enabled)
    }
    localStorage.setItem(SESSION_KEY, JSON.stringify(session))
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('tenantPortalAuthChanged'))
    }
    return session
  } catch {
    return current
  }
}

export function setPortalAuth(token: string, session: TenantPortalSession) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('tenantPortalAuthChanged'))
  }
}

export function clearPortalAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(SESSION_KEY)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('tenantPortalAuthChanged'))
  }
}

export function redirectToLogin() {
  clearPortalAuth()
  if (typeof window === 'undefined') return
  if (window.location.pathname.includes('/login')) return
  const parts = window.location.pathname.split('/').filter(Boolean)
  const locale = ['ru', 'kz', 'en'].includes(parts[0]) ? parts[0] : 'ru'
  window.location.href = `/${locale}/login`
}
