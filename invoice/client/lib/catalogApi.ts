import axios from 'axios'
import { tenantApiParams } from './tenantContext'
import { getPortalToken } from './tenantAuth'

import { getApiBaseUrl } from './apiBaseUrl'

const catalogClient = axios.create({
  timeout: 0,
  headers: { 'Content-Type': 'application/json' },
})

catalogClient.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl()
  const token = getPortalToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export interface CatalogTRC {
  id: number
  name: string
  is_active: boolean
  created_at: string
}

export interface CatalogTenant {
  id: number
  trc_id: number
  name: string
  legal_name: string
  org_type: string
  bin_value?: string
  iin_value?: string
  phone?: string
  is_active: boolean
}

type CounterpartyPhonesPayload = {
  phones: string[]
  phone_rent?: string | null
  phone_utilities?: string | null
  phone_operations?: string | null
  auto_notify_paused?: boolean
}

export const catalogApi = {
  getCounterpartyPhones: async (counterpartyId: string): Promise<CounterpartyPhonesPayload> => {
    const { data } = await catalogClient.get<CounterpartyPhonesPayload>(
      '/api/catalog/counterparty-phones',
      {
        params: { counterparty_id: counterpartyId, ...tenantApiParams() },
      },
    )
    return {
      phones: data.phones || [],
      phone_rent: data.phone_rent,
      phone_utilities: data.phone_utilities,
      phone_operations: data.phone_operations,
      auto_notify_paused: data.auto_notify_paused,
    }
  },
  updateCounterpartyPhoneRouting: async (
    counterpartyId: string,
    routing: { phone_rent?: string; phone_utilities?: string; phone_operations?: string },
    counterpartyName?: string,
  ): Promise<CounterpartyPhonesPayload> => {
    const { data } = await catalogClient.patch<CounterpartyPhonesPayload>(
      '/api/catalog/counterparty-phones/routing',
      {
        one_c_counterparty_id: counterpartyId,
        phone_rent: routing.phone_rent || null,
        phone_utilities: routing.phone_utilities || null,
        phone_operations: routing.phone_operations || null,
        counterparty_name: counterpartyName,
      },
      { params: tenantApiParams() },
    )
    return data
  },
  setAutoNotifyPaused: async (
    counterpartyId: string,
    paused: boolean,
    counterpartyName?: string,
  ): Promise<CounterpartyPhonesPayload> => {
    const { data } = await catalogClient.patch<CounterpartyPhonesPayload>(
      '/api/catalog/counterparty-phones/auto-notify',
      {
        one_c_counterparty_id: counterpartyId,
        paused,
        counterparty_name: counterpartyName,
      },
      { params: tenantApiParams() },
    )
    return data
  },
  setTenantAutoNotifyPaused: async (paused: boolean): Promise<{ auto_notify_paused: boolean }> => {
    const { data } = await catalogClient.patch<{ auto_notify_paused: boolean }>(
      '/api/catalog/tenant/auto-notify',
      { paused },
      { params: tenantApiParams() },
    )
    return data
  },
  appendCounterpartyPhone: async (
    counterpartyId: string,
    phone: string,
    counterpartyName?: string,
  ): Promise<CounterpartyPhonesPayload> => {
    const { data } = await catalogClient.post<CounterpartyPhonesPayload>(
      '/api/catalog/counterparty-phones',
      {
        one_c_counterparty_id: counterpartyId,
        phone,
        counterparty_name: counterpartyName,
      },
      { params: tenantApiParams() },
    )
    return data
  },
  listTrcs: async (): Promise<CatalogTRC[]> => {
    const { data } = await catalogClient.get<CatalogTRC[]>('/api/catalog/trcs')
    return data
  },
  listTenants: async (trcId: number): Promise<CatalogTenant[]> => {
    const { data } = await catalogClient.get<CatalogTenant[]>(
      `/api/catalog/trcs/${trcId}/tenants`,
    )
    return data
  },
}

export { tenantApiParams }
