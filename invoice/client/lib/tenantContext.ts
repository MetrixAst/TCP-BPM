import {
  getPortalSession,
  isPortalSession,
  isTenantPortalSession,
} from './tenantAuth'

const TRC_KEY = 'selected_trc_id'
const TENANT_KEY = 'selected_tenant_id'

export { isPortalSession, isTenantPortalSession }

export function getSelectedTrcId(): number | null {
  if (typeof window === 'undefined') return null
  const v = localStorage.getItem(TRC_KEY)
  return v ? Number(v) : null
}

export function getSelectedTenantId(): number | null {
  if (typeof window === 'undefined') return null
  const v = localStorage.getItem(TENANT_KEY)
  return v ? Number(v) : null
}

export function setSelectedTrcId(id: number | null) {
  if (id == null) localStorage.removeItem(TRC_KEY)
  else localStorage.setItem(TRC_KEY, String(id))
}

export function setSelectedTenantId(id: number | null) {
  if (id == null) localStorage.removeItem(TENANT_KEY)
  else localStorage.setItem(TENANT_KEY, String(id))
}

export function notifyTenantContextChanged() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('tenantContextChanged'))
  }
}

export function tenantApiParams(): { tenant_id?: number } {
  const portal = getPortalSession()
  if (portal) {
    if (portal.role === 'tenant' && portal.tenant_id) {
      return { tenant_id: portal.tenant_id }
    }
    if (portal.role === 'trc') {
      const tenantId = getSelectedTenantId()
      return tenantId ? { tenant_id: tenantId } : {}
    }
  }
  const tenantId = getSelectedTenantId()
  return tenantId ? { tenant_id: tenantId } : {}
}

export function getEffectiveTrcId(): number | null {
  const portal = getPortalSession()
  if (portal) return portal.trc_id
  return getSelectedTrcId()
}

export function getEffectiveTenantId(): number | null {
  const portal = getPortalSession()
  if (portal) {
    if (portal.role === 'tenant') return portal.tenant_id
    return getSelectedTenantId()
  }
  return getSelectedTenantId()
}
