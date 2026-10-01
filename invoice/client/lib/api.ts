import axios from 'axios'
import { getApiBaseUrl, API_URL } from './apiBaseUrl'
import { tenantApiParams } from './tenantContext'
import { getPortalToken, redirectToLogin } from './tenantAuth'

export { API_URL, getApiBaseUrl }

// Дефолт на случай зависшего бэка/1С — раньше timeout:0 (без таймаута вообще)
// означал, что запрос мог висеть бесконечно без возможности восстановиться
// без перезагрузки страницы. Точечные вызовы с более длинными операциями
// (sendDebtorsBulk, sendInvoiceEmail, live-источники 1С) уже сами
// переопределяют timeout в своих запросах — этот дефолт их не трогает.
const DEFAULT_TIMEOUT_MS = 30000

const api = axios.create({
  timeout: DEFAULT_TIMEOUT_MS,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl()
  const token = getPortalToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const url = String(error.config?.url || '')
    if (
      status === 401 &&
      getPortalToken() &&
      !url.includes('/api/tenant-auth/login')
    ) {
      redirectToLogin()
    }
    return Promise.reject(error)
  },
)

export interface TenantPortalLoginResponse {
  access_token: string
  token_type: string
  role: 'tenant' | 'trc'
  tenant_id: number | null
  trc_id: number
  tenant_name: string
  trc_name: string
  legal_name: string
}

export interface TenantPortalMeResponse {
  role: 'tenant' | 'trc'
  tenant_id: number | null
  trc_id: number
  tenant_name: string
  trc_name: string
  legal_name: string
  payment_types_enabled?: {
    rent?: boolean
    utilities?: boolean
    operations?: boolean
  }
  xlsx_upload_available?: boolean
}

export const tenantAuthApi = {
  login: async (username: string, password: string): Promise<TenantPortalLoginResponse> => {
    const response = await api.post<TenantPortalLoginResponse>('/api/tenant-auth/login', {
      username,
      password,
    })
    return response.data
  },
  me: async (): Promise<TenantPortalMeResponse> => {
    const response = await api.get<TenantPortalMeResponse>('/api/tenant-auth/me')
    return response.data
  },
}

function withTenantParams<T extends Record<string, unknown>>(params?: T) {
  return { ...params, ...tenantApiParams() }
}

export interface Payment {
  id: number
  ip_name: string
  tenant_name: string
  invoice_date: string
  due_date: string
  paid_at: string | null
  status: 'paid' | 'partial' | 'unpaid' | 'overdue'
  period: string
  amount: number | null
  paid_amount?: number | null
  invoice_id?: string | null
  counterparty_id?: string | null
  /** "rent"/"utilities"/"operations"/"signage"/"assp", через запятую если счёт
   *  содержит строки нескольких типов, "unknown" если не распознано, null/undefined
   *  если строка ещё не досинхронизирована (см. invoice_service_type.py). */
  service_type?: string | null
  notifications?: Notification[]
}

export interface Notification {
  queued?: boolean
  whatsapp_sent?: boolean
  id: number
  payment_id: number
  notification_type: 'week_before' | 'three_days' | 'same_day' | 'overdue'
  status: 'sent' | 'delivered' | 'read'
  sent_at: string
  delivered_at: string | null
  read_at: string | null
  phone_number: string | null
}

export interface PaymentFilter {
  period?: string
  date_from?: string
  date_to?: string
  ip_name?: string
  tenant_name?: string
  status?: 'paid' | 'partial' | 'unpaid' | 'overdue' | 'test'
  /** "rent" | "utilities" | "operations" | "signage" | "assp" — матчится по
   *  подстроке на бэкенде, так что счёт с несколькими типами находится по любому. */
  service_type?: string
  page?: number
  page_size?: number
}

export interface PaymentSyncStatus {
  status: 'idle' | 'queued' | 'started' | 'running' | 'done' | 'failed'
  period?: string
  message?: string
  error?: string | null
  records?: number | null
  started_at?: string | null
  finished_at?: string | null
}

export interface PaymentListResponse {
  items: Payment[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface PaymentAnalytics {
  total_tenants: number
  total_invoices?: number
  paid: number
  partial?: number
  unpaid: number
  overdue: number
  source?: string
  // Какие service_type реально есть хоть в одном счёте текущего периода —
  // независимо от выбранного фильтра типа. См. InvoiceRegistryTable.tsx
  // (скрывает из фильтра типы без данных, напр. АССП/долг/прочее).
  service_types_present?: string[]
}

export interface XlsxImportSummary {
  file_id: number
  tenant_id: number
  periods: string[]
  rows_total: number
  rows_created: number
  rows_updated: number
  // Полная замена, не патч — старые xlsx-строки этого арендатора, которых
  // нет в новом файле, удаляются на бэкенде (см. xlsx_import/upsert.py).
  rows_deleted: number
  rows_matched: number
  rows_unmatched: number
  unmatched_names: string[]
  totals_check: Record<string, { expected: number; actual: number; diff: number; ok: boolean }>
  warnings: string[]
}

export const xlsxImportApi = {
  upload: async (file: File): Promise<XlsxImportSummary> => {
    const form = new FormData()
    form.append('file', file)
    const response = await api.post<XlsxImportSummary>('/api/xlsx-import/upload', form, {
      params: withTenantParams({}),
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
    return response.data
  },
}

export const paymentApi = {
  getPayments: async (filters: PaymentFilter = {}): Promise<PaymentListResponse> => {
    const response = await api.get<PaymentListResponse>('/api/payments', {
      params: withTenantParams(filters as Record<string, unknown>),
    })
    return response.data
  },

  startSyncFrom1C: async (period: string): Promise<PaymentSyncStatus> => {
    const response = await api.post<PaymentSyncStatus>('/api/payments/sync', null, {
      params: withTenantParams({ period }),
      timeout: 30000,
    })
    return response.data
  },

  getSyncStatus: async (period: string): Promise<PaymentSyncStatus> => {
    const response = await api.get<PaymentSyncStatus>('/api/payments/sync-status', {
      params: withTenantParams({ period }),
      timeout: 15000,
    })
    return response.data
  },

  getAnalytics: async (
    filters: {
      period?: string
      date_from?: string
      date_to?: string
      ip_name?: string
      tenant_name?: string
      status?: PaymentFilter['status']
    } = {},
  ): Promise<PaymentAnalytics> => {
    const response = await api.get<PaymentAnalytics>('/api/payments/analytics', {
      params: withTenantParams(filters),
      timeout: 30000,
    })
    return response.data
  },

  getPaymentNotifications: async (paymentId: number): Promise<Notification[]> => {
    const response = await api.get<Notification[]>(`/api/payments/${paymentId}/notifications`)
    return response.data
  },

  exportPayments: async (filters: PaymentFilter = {}): Promise<Blob> => {
    const response = await api.get('/api/payments/export', {
      params: withTenantParams(filters as Record<string, unknown>),
      responseType: 'blob',
    })
    return response.data
  },

  sendNotification: async (
    notificationType: string,
    phoneNumber: string,
    counterpartyId: string,
    invoiceId?: string,
    paymentId?: number,
    options?: { immediate?: boolean; serviceType?: string },
  ): Promise<Notification> => {
    const response = await api.post<Notification>(
      '/api/notifications/send',
      {
        ...(paymentId != null ? { payment_id: paymentId } : {}),
        notification_type: notificationType,
        phone_number: phoneNumber,
        counterparty_id: counterpartyId,
        ...(invoiceId ? { invoice_id: invoiceId } : {}),
        ...(options?.serviceType ? { service_type: options.serviceType } : {}),
      },
      {
        params: withTenantParams({
          immediate: options?.immediate === true,
        }),
        timeout: 60000,
      },
    )
    return response.data
  },

  sendQuickMessage: async (
    counterpartyId: string,
    phoneNumber: string,
    message: string,
  ): Promise<{ success: boolean; error?: string }> => {
    const response = await api.post<{ success: boolean; error?: string }>(
      '/api/notifications/send-quick-message',
      {
        counterparty_id: counterpartyId,
        phone_number: phoneNumber,
        message,
      },
      {
        params: withTenantParams({}),
        timeout: 30000,
      },
    )
    return response.data
  },

  sendDebtorsBulk: async (opts: {
    period?: string
    date_from?: string
    date_to?: string
    ignore_balance_filter?: boolean
    /** Пусто/не передано — как раньше, все типы, найденные в счёте */
    service_types?: string[]
    /** Сузить до одного контрагента — кнопка «Отправить все счета» на карточке контрагента */
    counterpartyId?: string
  }): Promise<{
    queued: number
    skipped_no_phone: number
    skipped_no_service: number
    skipped_service_type_filtered: number
    skipped_no_invoice: number
    debtor_invoices: number
    errors: number
    message: string
  }> => {
    const response = await api.post(
      '/api/notifications/send-debtors',
      {
        ...(opts.period ? { period: opts.period } : {}),
        ...(opts.date_from ? { date_from: opts.date_from } : {}),
        ...(opts.date_to ? { date_to: opts.date_to } : {}),
        ...(opts.ignore_balance_filter ? { ignore_balance_filter: true } : {}),
        ...(opts.service_types && opts.service_types.length
          ? { service_types: opts.service_types }
          : {}),
        ...(opts.counterpartyId ? { counterparty_id: opts.counterpartyId } : {}),
      },
      {
        params: withTenantParams({}),
        timeout: 300000,
      },
    )
    return response.data
  },

  sendInvoiceEmail: async (opts: {
    counterpartyId: string
    email?: string
    invoiceId?: string
    serviceType?: string
    counterpartyName?: string
  }): Promise<{ ok: boolean; message: string; email?: string; invoice_id?: string }> => {
    const response = await api.post(
      '/api/notifications/send-email',
      {
        counterparty_id: opts.counterpartyId,
        ...(opts.email ? { email: opts.email } : {}),
        ...(opts.invoiceId ? { invoice_id: opts.invoiceId } : {}),
        ...(opts.serviceType ? { service_type: opts.serviceType } : {}),
        ...(opts.counterpartyName ? { counterparty_name: opts.counterpartyName } : {}),
      },
      {
        params: withTenantParams({}),
        timeout: 120000,
      },
    )
    return response.data
  },

  get1CInvoices: async (
    period?: string,
    limit: number = 10000,
    counterpartyId?: string,
    source: 'db' | 'live' = 'db',
  ): Promise<{ 
    invoices: Array<{ 
      id: string
      number: string
      date: string
      counterparty_name?: string
      counterparty_id?: string
      counterparty?: {
        id: string
        name: string
        bin: string
      }
      amount: number
      vat?: number
      currency: string
      status: string
      paid_amount?: number
      pdf?: string
      pdf_downloaded?: boolean
      pdf_file_path?: string
      items: Array<{
        name: string
        quantity: number
        price: number
        amount: number
      }>
    }>
    error?: string
    warning?: string
    source?: string
  }> => {
    const response = await api.get('/api/payments/1c/invoices', {
      params: withTenantParams({
        ...(period ? { period } : {}),
        limit,
        source,
        ...(counterpartyId ? { counterparty_id: counterpartyId } : {}),
      }),
      timeout: source === 'live' ? 120000 : 30000,
    })
    return response.data
  },

  download1CInvoice: async (
    invoiceId: string,
    counterpartyId: string,
  ): Promise<Blob> => {
    const response = await api.get(`/api/payments/1c/invoices/${invoiceId}/download`, {
      params: withTenantParams({ counterparty_id: counterpartyId }),
      responseType: 'blob',
    })
    return response.data
  },

  // Строки из xlsx-импорта (invoice.source === 'xlsx') не проходят проверку
  // владения через 1С — синтетический invoice_id ("xlsx:...") никогда не
  // совпадёт с реальным 1С-счётом, поэтому это отдельный backend-эндпоинт,
  // не /1c/invoices/{id}/download (см. app/services/xlsx_invoice_pdf.py).
  downloadXlsxInvoice: async (invoiceId: string): Promise<Blob> => {
    const response = await api.get(
      `/api/payments/xlsx/${encodeURIComponent(invoiceId)}/download`,
      {
        params: withTenantParams({}),
        responseType: 'blob',
      },
    )
    return response.data
  },
}

export interface DataRecord {
  id: string
  type: string
  data: Record<string, any>
}

export interface DataResponse {
  data: DataRecord[]
  has_more: boolean
  sync_token: string | null
  error?: string
}

export interface BalanceDetail {
  receivable: number
  payable: number
  net: number
}

export interface AgingDetail {
  period: string
  amount: number
}

export interface Balance {
  counterparty: Record<string, any>
  balances: BalanceDetail
  aging: AgingDetail[]
  documents: Record<string, any>[]
  by_documents?: Array<{
    type: string
    document: string
    date: string
    amount: number
    paid: number
    debt: number
  }>
  date?: string
  error?: string
}

export interface BankAccount {
  id: string
  bank_name: string
  bank_bik: string
  account_number: string
  currency: string
  is_default: boolean
}

export interface Contract {
  id: string
  number: string
  date: string
  type: string
  status: string
}

export interface CounterpartyLatestInvoice {
  invoiceId?: string
  invoiceNumber?: string
  invoiceDate?: string
  dueDate?: string
  documentStatus?: string
  paymentStatus?: 'paid' | 'partial' | 'unpaid' | 'overdue'
  paidAt?: string | null
  amount?: number
  paidAmount?: number | null
}

export interface Counterparty {
  id: string
  fullName: string
  latestInvoice?: CounterpartyLatestInvoice
  paymentDueDays?: {
    rent?: number
    utilities?: number
    operations?: number
  }
  paymentTypesEnabled?: {
    rent?: boolean
    utilities?: boolean
    operations?: boolean
  }
  bin?: string
  iin?: string
  address?: string
  phone?: string
  phoneNumber?: string
  contactPerson?: string
  phoneFromCatalog?: boolean
  /** Последняя успешная отправка WhatsApp этому контрагенту (ISO), любого вида
   *  рассылки — ручная, массовая должникам, авто-напоминание или файл. */
  lastWhatsappSentAt?: string | null
  /** Авто-рассылка (почасовые WhatsApp-напоминания) поставлена на паузу для
   *  этого контрагента. Не влияет на ручную отправку и массовую /send-debtors. */
  autoNotifyPaused?: boolean
  email?: string
  website?: string
  bankAccounts: BankAccount[]
  contracts: Contract[]
  invoiceCount?: number
  /** BUH balance: нам должны (1210) */
  balanceDebit?: number
  /** BUH balance: аванс / мы должны (3510) */
  balanceCredit?: number
  /** debit − credit */
  balanceNet?: number
  /** debt | advance | zero */
  balanceLabel?: 'debt' | 'advance' | 'zero' | string

  govEntity?: boolean
  vatCertDate?: string
  kbe?: string
  vatCertNo?: string
  rnn?: string
  vatSeries?: string
  residencyCountry?: string
  counterpartyType?: string
  accountNumber?: string
  bic?: string
  contractNumber?: string
  contractDate?: string
  currency?: string
  priceType?: string
  /** Id папки/группы справочника (Родитель) */
  folderId?: string
  /** Наименование папки (fullName группы в 1С) */
  folderName?: string
}

export interface CounterpartyFolder {
  id?: string
  fullName: string
}

export interface CounterpartiesResponse {
  counterparties: Counterparty[]
  folders?: CounterpartyFolder[]
  paymentTypesEnabled?: {
    rent?: boolean
    utilities?: boolean
    operations?: boolean
  }
  /** «Отключить авто-напоминания для всех» — пауза на уровне арендатора,
   *  независимо от точечных Counterparty.autoNotifyPaused. */
  tenantAutoNotifyPaused?: boolean
  error?: string
  warning?: string
  sync_error?: string
  sync_status?: string
  total_from_1c?: number
  source?: string
  /** когда последний раз подтянули BUH balance */
  balance_synced_at?: string
}

export interface ConfirmRequest {
  received_ids: string[]
  status?: string
  errors?: string[]
  sync_token?: string | null
}

export interface ConfirmResponse {
  success: boolean
  confirmed: number
  failed: number
  error?: string
}

export const oneCApi = {

  getData: async (limit: number = 100): Promise<DataResponse> => {
    const response = await api.get<DataResponse>('/api/1c/data', {
      params: withTenantParams({ limit }),
    })
    return response.data
  },


  getBalance: async (counterpartyId: string, since?: string): Promise<Balance> => {
    const response = await api.get<Balance>('/api/1c/balance', {
      params: withTenantParams({
        counterparty_id: counterpartyId,
        ...(since && { since }),
      }),
    })
    return response.data
  },


  getCounterparties: async (
    limit: number = 10000,
    options?: { include_invoice_status?: boolean; period?: string },
  ): Promise<CounterpartiesResponse> => {
    const response = await api.get<CounterpartiesResponse>('/api/1c/counterparties', {
      params: withTenantParams({
        limit,
        include_invoice_status: options?.include_invoice_status ?? false,
        ...(options?.period ? { period: options.period } : {}),
      }),
    })
    return response.data
  },

  syncCounterparties: async (): Promise<{
    ok: boolean
    count: number
    status?: string
    message?: string
    error?: string
  }> => {
    const response = await api.post<{
      ok: boolean
      count: number
      status?: string
      message?: string
      error?: string
    }>(
      '/api/1c/counterparties/sync',
      {},
      { params: tenantApiParams(), timeout: 30000 },
    )
    return response.data
  },


  confirm: async (request: ConfirmRequest): Promise<ConfirmResponse> => {
    const response = await api.post<ConfirmResponse>('/api/1c/confirm', request, {
      params: tenantApiParams(),
    })
    return response.data
  },
}
