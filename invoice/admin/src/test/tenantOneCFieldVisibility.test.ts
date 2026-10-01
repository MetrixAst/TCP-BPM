import { describe, expect, it } from 'vitest'
import { tenantShowsNovaComFields, tenantShowsODataFields } from '../App'

/**
 * These two functions decide which 1C-connection fields the admin sees for a
 * given tenant.one_c_connection_mode — the exact screen where the ИП MOON
 * misconfiguration (odata_direct mode saved with an empty one_c_base_url,
 * silently falling back to an unrelated global OData server, see
 * app/services/tenant_1c.py) was set. The backend now rejects that combination
 * outright, but the field-visibility rules are the first line of defense: an
 * admin choosing "OData напрямую" should still see the base_url field to fill in.
 */
describe('tenantShowsNovaComFields', () => {
  it('hides Nova/COM org fields only in odata_direct mode', () => {
    expect(tenantShowsNovaComFields('odata_direct')).toBe(false)
  })

  it('shows Nova/COM org fields in nova_org mode', () => {
    expect(tenantShowsNovaComFields('nova_org')).toBe(true)
  })

  it('shows Nova/COM org fields in auto mode', () => {
    expect(tenantShowsNovaComFields('auto')).toBe(true)
  })
})

describe('tenantShowsODataFields', () => {
  it('shows the OData base_url field in odata_direct mode', () => {
    expect(tenantShowsODataFields('odata_direct')).toBe(true)
  })

  it('hides the OData base_url field only in nova_org mode', () => {
    expect(tenantShowsODataFields('nova_org')).toBe(false)
  })

  it('shows the OData base_url field in auto mode', () => {
    expect(tenantShowsODataFields('auto')).toBe(true)
  })
})

describe('field visibility never hides base_url for the exact incident mode', () => {
  it('odata_direct always shows base_url, so an empty value is a visible, fixable gap — not a silent one', () => {
    expect(tenantShowsODataFields('odata_direct')).toBe(true)
  })
})
