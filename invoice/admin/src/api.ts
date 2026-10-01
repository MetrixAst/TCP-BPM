import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8004'

const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
})

export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`
  } else {
    delete api.defaults.headers.common.Authorization
  }
}

export interface TRC {
  id: number
  name: string
  phone?: string | null
  bin_value?: string | null
  iin_value?: string | null
  message_template?: string | null
  green_api_url?: string | null
  green_api_media_url?: string | null
  green_api_id_instance?: string | null
  green_api_api_token?: string
  portal_username?: string | null
  is_active: boolean
  created_at: string
}

export interface Tenant {
  id: number
  trc_id: number
  name: string
  legal_name: string
  org_type: string
  bin_value?: string | null
  iin_value?: string | null
  phone?: string | null
  message_template?: string | null
  green_api_url?: string | null
  green_api_media_url?: string | null
  green_api_id_instance?: string | null
  green_api_api_token?: string
  one_c_counterparty_id?: string | null
  one_c_name_match?: string | null
  one_c_login: string
  one_c_base_url?: string | null
  one_c_basic_user?: string | null
  one_c_basic_password?: string
  nova_organization_id?: number | null
  nova_mcp_system_type?: string | null
  nova_script_invoices?: number | null
  nova_script_payments?: number | null
  nova_script_counterparties?: number | null
  nova_script_balance?: number | null
  nova_script_invoice_by_id?: number | null
  one_c_connection_mode?: string | null
  xlsx_priority?: string | null
  xlsx_parser_key?: string | null
  portal_username?: string | null
  stamp_file_path?: string | null
  signature_file_path?: string | null
  invoice_executor_name?: string | null
  invoice_iik?: string | null
  invoice_kbe?: string | null
  invoice_bank_name?: string | null
  invoice_bank_bik?: string | null
  invoice_payment_knp?: string | null
  invoice_supplier_address?: string | null
  invoice_contract_text?: string | null
  invoice_due_day?: number | null
  invoice_due_day_utilities?: number | null
  invoice_due_day_operations?: number | null
  payment_rent_enabled?: boolean
  payment_utilities_enabled?: boolean
  payment_operations_enabled?: boolean
  smtp_host?: string | null
  smtp_port?: number | null
  smtp_use_starttls?: boolean
  smtp_username?: string | null
  smtp_from_email?: string | null
  has_one_c_password?: boolean
  has_one_c_basic_password?: boolean
  has_green_api_api_token?: boolean
  has_smtp_password?: boolean
  is_active: boolean
  created_at: string
}


export type TenantCreatePayload = {
  name: string
  legal_name: string
  org_type: string
  bin_value?: string | null
  iin_value?: string | null
  phone?: string | null
  message_template?: string | null
  green_api_url?: string | null
  green_api_media_url?: string | null
  green_api_id_instance?: string | null
  green_api_api_token?: string
  one_c_counterparty_id?: string | null
  one_c_name_match?: string | null
  one_c_login: string
  one_c_password: string
  one_c_base_url?: string | null
  one_c_basic_user?: string | null
  one_c_basic_password?: string
  nova_organization_id?: number | null
  nova_mcp_system_type?: string
  nova_script_invoices?: number
  nova_script_payments?: number
  nova_script_counterparties?: number
  nova_script_balance?: number
  nova_script_invoice_by_id?: number
  one_c_connection_mode?: string
  xlsx_priority?: string
  xlsx_parser_key?: string | null
  portal_username?: string
  portal_password?: string
  invoice_iik?: string | null
  invoice_kbe?: string | null
  invoice_bank_name?: string | null
  invoice_bank_bik?: string | null
  invoice_payment_knp?: string | null
  invoice_executor_name?: string | null
  invoice_supplier_address?: string | null
  invoice_contract_text?: string | null
  invoice_due_day?: number | null
  invoice_due_day_utilities?: number | null
  invoice_due_day_operations?: number | null
  payment_rent_enabled?: boolean
  payment_utilities_enabled?: boolean
  payment_operations_enabled?: boolean
  smtp_host?: string | null
  smtp_port?: number | null
  smtp_use_starttls?: boolean
  smtp_username?: string | null
  smtp_password?: string
  smtp_from_email?: string | null
  is_active: boolean
}

export interface NovaOrgResolveResult {
  organization_id: number
  organization_name?: string | null
  connection_mode: string
  nova_mcp_system_type?: string | null
  nova_script_invoices?: number | null
  nova_script_payments?: number | null
  nova_script_counterparties?: number | null
  nova_script_balance?: number | null
  nova_script_invoice_by_id?: number | null
  odata_url?: string | null
  one_c_login?: string | null
  database_name?: string | null
  agent_id?: string | null
  password_required: boolean
  message: string
  test_ok: boolean
  counterparties_count?: number | null
  error?: string | null
}

export const adminApi = {
  login: async (username: string, password: string) => {
    const { data } = await api.post<{ access_token: string }>('/api/admin/auth/login', {
      username,
      password,
    })
    return data
  },
  me: async () => {
    const { data } = await api.get<AdminUserResponse>('/api/admin/me')
    return data
  },
  listTrcs: async () => {
    const { data } = await api.get<TRC[]>('/api/admin/trcs')
    return data
  },
  createTrc: async (payload: Omit<TRC, 'id' | 'created_at'>) => {
    const { data } = await api.post<TRC>('/api/admin/trcs', payload)
    return data
  },
  updateTrc: async (id: number, payload: Partial<TRC> & { portal_password?: string }) => {
    const { data } = await api.patch<TRC>(`/api/admin/trcs/${id}`, payload)
    return data
  },
  getTrc: async (id: number) => {
    const { data } = await api.get<TRC>(`/api/admin/trcs/${id}`)
    return data
  },
  deleteTrc: async (id: number) => {
    await api.delete(`/api/admin/trcs/${id}`)
  },
  listTenants: async (trcId: number) => {
    const { data } = await api.get<Tenant[]>(`/api/admin/trcs/${trcId}/tenants`)
    return data
  },
  createTenant: async (trcId: number, payload: TenantCreatePayload) => {
    const { data } = await api.post<Tenant>(`/api/admin/trcs/${trcId}/tenants`, payload)
    return data
  },
  updateTenant: async (
    trcId: number,
    tenantId: number,
    payload: Partial<Tenant> & { smtp_password?: string; portal_password?: string },
  ) => {
    const { data } = await api.patch<Tenant>(
      `/api/admin/trcs/${trcId}/tenants/${tenantId}`,
      payload,
    )
    return data
  },
  testTenantSmtp: async (
    trcId: number,
    tenantId: number,
    payload: {
      smtp_host?: string
      smtp_port?: number
      smtp_use_starttls?: boolean
      smtp_username?: string
      smtp_password?: string
      smtp_from_email?: string
      send_to?: string
    },
  ) => {
    const { data } = await api.post<{ ok: boolean; message?: string; error?: string }>(
      `/api/admin/trcs/${trcId}/tenants/${tenantId}/smtp/test`,
      payload,
    )
    return data
  },
  uploadTenantStamp: async (trcId: number, tenantId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post<Tenant>(
      `/api/admin/trcs/${trcId}/tenants/${tenantId}/stamp`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return data
  },
  removeTenantStamp: async (trcId: number, tenantId: number) => {
    const { data } = await api.delete<Tenant>(`/api/admin/trcs/${trcId}/tenants/${tenantId}/stamp`)
    return data
  },
  uploadTenantSignature: async (trcId: number, tenantId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post<Tenant>(
      `/api/admin/trcs/${trcId}/tenants/${tenantId}/signature`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return data
  },
  removeTenantSignature: async (trcId: number, tenantId: number) => {
    const { data } = await api.delete<Tenant>(
      `/api/admin/trcs/${trcId}/tenants/${tenantId}/signature`,
    )
    return data
  },
  deleteTenant: async (trcId: number, tenantId: number) => {
    await api.delete(`/api/admin/trcs/${trcId}/tenants/${tenantId}`)
  },
  loadCounterpartyDirectory: async (trcId: number, tenantId?: number) => {
    const { data } = await api.get<CounterpartyDirectoryItem[]>(
      `/api/admin/trcs/${trcId}/counterparty-directory`,
      { params: tenantId ? { tenant_id: tenantId } : {} },
    )
    return data
  },
  // Параллельный источник для арендаторов без 1С вообще — counterparty-directory
  // всегда 503 для них (кэш 1С никогда не наполнится). tenantId обязателен
  // (в отличие от loadCounterpartyDirectory) — нет "первого арендатора ТРЦ" по
  // умолчанию, xlsx-контрагенты жёстко привязаны к конкретному арендатору.
  loadCounterpartyDirectoryXlsx: async (trcId: number, tenantId: number) => {
    const { data } = await api.get<CounterpartyDirectoryItem[]>(
      `/api/admin/trcs/${trcId}/counterparty-directory-xlsx`,
      { params: { tenant_id: tenantId } },
    )
    return data
  },
  saveCounterpartyPhones: async (trcId: number, items: CounterpartyPhoneUpsert[], tenantId?: number) => {
    const { data } = await api.put<CounterpartyPhoneResponse[]>(
      `/api/admin/trcs/${trcId}/counterparty-phones`,
      items,
      { params: tenantId ? { tenant_id: tenantId } : {} },
    )
    return data
  },
  resolveNovaOrg: async (organizationId: number, test = true) => {
    const { data } = await api.get<NovaOrgResolveResult>(
      `/api/admin/nova/organizations/${organizationId}/resolve`,
      { params: { test } },
    )
    return data
  },

  getTrcDebtSummary: async (trcId: number) => {
    const { data } = await api.get<TrcDebtSummary>(`/api/admin/trcs/${trcId}/debt-summary`)
    return data
  },

  // --- Counterparty phone book: delete + 1C backfill ---
  listCounterpartyPhones: async (trcId: number) => {
    const { data } = await api.get<CounterpartyPhoneResponse[]>(
      `/api/admin/trcs/${trcId}/counterparty-phones`,
    )
    return data
  },
  deleteCounterpartyPhone: async (trcId: number, phoneId: number) => {
    await api.delete(`/api/admin/trcs/${trcId}/counterparty-phones/${phoneId}`)
  },
  syncCounterpartyPhonesToOneC: async (
    trcId: number,
    params: { tenantId: number; dryRun?: boolean; limit?: number; afterId?: number },
  ) => {
    const { data } = await api.post<CounterpartyPhoneBackfillResponse>(
      `/api/admin/trcs/${trcId}/counterparty-phones/sync-to-1c`,
      null,
      {
        params: {
          tenant_id: params.tenantId,
          dry_run: params.dryRun ?? false,
          limit: params.limit ?? 0,
          after_id: params.afterId ?? 0,
        },
      },
    )
    return data
  },

  // --- Auto-notifications: manual trigger (super-admin only) ---
  runAutoNotifications: async (payload: AutoNotificationRunPayload) => {
    const { data } = await api.post<AutoNotificationRunResponse>(
      '/api/admin/auto-notifications/run',
      payload,
    )
    return data
  },

  // --- Admin users: create (super-admin only) ---
  createAdminUser: async (payload: AdminUserCreatePayload) => {
    const { data } = await api.post<AdminUserResponse>('/api/admin/users', payload)
    return data
  },

  // --- WhatsApp send log ---
  getWhatsAppLog: async (
    trcId: number,
    params: { tenantId?: number; dateFrom?: string; dateTo?: string; limit?: number; offset?: number },
  ) => {
    const { data } = await api.get<WhatsAppLogResponse>(`/api/admin/trcs/${trcId}/whatsapp-log`, {
      params: {
        tenant_id: params.tenantId || undefined,
        date_from: params.dateFrom || undefined,
        date_to: params.dateTo || undefined,
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
      },
    })
    return data
  },
}

export interface CounterpartyDirectoryItem {
  one_c_counterparty_id: string
  counterparty_name: string
  contact_name?: string
  phone?: string
  bin_value?: string
}

export interface AgingBuckets {
  current: number
  days30: number
  days60: number
  days90: number
  over120: number
  unknown: number
  total: number
}

export interface TenantDebtSummary {
  tenant_id: number
  tenant_name: string
  has_balance_data: boolean
  synced_at?: string | null
  debt: number
  advance: number
  aging: AgingBuckets
}

export interface TrcDebtSummary {
  trc_id: number
  total_debt: number
  total_advance: number
  aging: AgingBuckets
  tenants_with_data: number
  tenants_without_data: number
  by_tenant: TenantDebtSummary[]
}

export interface CounterpartyPhoneUpsert {
  one_c_counterparty_id: string
  counterparty_name?: string
  contact_name?: string
  phone: string
}

export interface CounterpartyPhoneResponse extends CounterpartyPhoneUpsert {
  id: number
  trc_id: number
  phone_rent?: string | null
  phone_utilities?: string | null
  phone_operations?: string | null
  last_whatsapp_sent_at?: string | null
}

export interface CounterpartyPhoneBackfillItem {
  one_c_counterparty_id: string
  counterparty_name?: string
  phones: string[]
  status: 'would_write' | 'empty_skip' | 'ok' | 'fail'
  written?: number
  skipped?: number
  message?: string
}

export interface CounterpartyPhoneBackfillResponse {
  ok: boolean
  error?: string
  dry_run: boolean
  tenant_id?: number
  tenant_name?: string
  trc_id?: number
  total: number
  ok_count: number
  fail_count: number
  empty_skip: number
  cache_refreshed: boolean
  last_processed_id?: number
  items: CounterpartyPhoneBackfillItem[]
}

export interface AutoNotificationRunPayload {
  tenant_id?: number
  force_window?: boolean
}

export interface AutoNotificationRunResponse {
  sent: number
  can_send: boolean
  tenant_id?: number
}

export interface AdminUserResponse {
  id: number
  username: string
  is_super: boolean
  is_active: boolean
}

export interface AdminUserCreatePayload {
  username: string
  password: string
}

export interface WhatsAppLogEntry {
  source: 'manual' | 'auto'
  sent_at: string
  phone_number?: string | null
  counterparty_name?: string | null
  ip_name?: string | null
  invoice_id?: string | null
  notification_type?: string | null
  service_type?: string | null
  status?: string | null
}

export interface WhatsAppLogResponse {
  items: WhatsAppLogEntry[]
  total: number
}

