import { useEffect, useState } from 'react'
import { Building2, Users, Phone, Send, UserPlus, LogOut, MessageSquare } from 'lucide-react'
import {
  adminApi,
  TRC,
  Tenant,
  TenantCreatePayload,
  CounterpartyDirectoryItem,
} from './api'
import { useAdminSession } from './hooks/useAdminSession'
import { useToast } from './lib/toast'
import { Tabs, type TabDef } from './components/layout/Tabs'
import { SavedPhonesCard } from './components/phonebook/SavedPhonesCard'
import { BackfillPanel } from './components/phonebook/BackfillPanel'
import { AutoNotifyPanel } from './components/admin/AutoNotifyPanel'
import { AdminUserCreatePanel } from './components/admin/AdminUserCreatePanel'
import { WhatsAppLogPanel } from './components/notifications/WhatsAppLogPanel'
import { DebtSummaryCard } from './components/tenants/DebtSummaryCard'

type TabKey = 'trc' | 'tenants' | 'phonebook' | 'whatsapplog' | 'autonotify' | 'adminusers'

const SELECTED_TRC_KEY = 'admin_selected_trc_id'

const defaultTrcTemplate = `Добрый день!

Направляем вам счёт за аренду. Подробности в приложенном документе.

{details}

С уважением,
{trc_name}`

const defaultTenantTemplate = `Направляем вам счёт за аренду. Подробности в приложенном документе.

{details}

С уважением,
{tenant_name}`

const emptyTrcForm = {
  name: '',
  phone: '',
  bin_value: '',
  iin_value: '',
  message_template: defaultTrcTemplate,
  green_api_url: 'https://7107.api.greenapi.com',
  green_api_media_url: 'https://7107.api.greenapi.com',
  green_api_id_instance: '',
  green_api_api_token: '',
  portal_username: '',
  portal_password: '',
  is_active: true,
}

const NOVA_SCRIPT_DEFAULTS = {
  odata: {
    nova_script_invoices: '11',
    nova_script_payments: '12',
    nova_script_counterparties: '13',
    nova_script_balance: '14',
    nova_script_invoice_by_id: '15',
  },
  com: {
    nova_script_invoices: '16',
    nova_script_payments: '17',
    nova_script_counterparties: '18',
    nova_script_balance: '19',
    nova_script_invoice_by_id: '20',
  },
} as const

type NovaMcpSystemType = keyof typeof NOVA_SCRIPT_DEFAULTS

type NovaScriptFormFields = {
  nova_mcp_system_type: NovaMcpSystemType
  nova_script_invoices: string
  nova_script_payments: string
  nova_script_counterparties: string
  nova_script_balance: string
  nova_script_invoice_by_id: string
}

function novaScriptFormDefaults(mcpType: NovaMcpSystemType): NovaScriptFormFields {
  const defaults = NOVA_SCRIPT_DEFAULTS[mcpType]
  return {
    nova_mcp_system_type: mcpType,
    nova_script_invoices: defaults.nova_script_invoices,
    nova_script_payments: defaults.nova_script_payments,
    nova_script_counterparties: defaults.nova_script_counterparties,
    nova_script_balance: defaults.nova_script_balance,
    nova_script_invoice_by_id: defaults.nova_script_invoice_by_id,
  }
}

function parseNovaScriptId(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) return undefined
  const n = Number(trimmed)
  return Number.isInteger(n) && n > 0 ? n : undefined
}

function tenantNovaScriptFields(
  tenant: Tenant,
  mcpType: NovaMcpSystemType = (tenant.nova_mcp_system_type as NovaMcpSystemType) || 'com',
): NovaScriptFormFields {
  const defaults = NOVA_SCRIPT_DEFAULTS[mcpType]
  // Prefer saved per-tenant ids; fall back to MCP defaults only when unset in DB.
  const pick = (saved: number | null | undefined, fallback: string) =>
    saved != null && saved > 0 ? String(saved) : fallback
  return {
    nova_mcp_system_type: mcpType,
    nova_script_invoices: pick(tenant.nova_script_invoices, defaults.nova_script_invoices),
    nova_script_payments: pick(tenant.nova_script_payments, defaults.nova_script_payments),
    nova_script_counterparties: pick(
      tenant.nova_script_counterparties,
      defaults.nova_script_counterparties,
    ),
    nova_script_balance: pick(tenant.nova_script_balance, defaults.nova_script_balance),
    nova_script_invoice_by_id: pick(
      tenant.nova_script_invoice_by_id,
      defaults.nova_script_invoice_by_id,
    ),
  }
}

const emptyTenantForm = {
  name: '',
  legal_name: '',
  org_type: 'IP',
  bin_value: '',
  iin_value: '',
  phone: '',
  message_template: defaultTenantTemplate,
  green_api_url: '',
  green_api_media_url: '',
  green_api_id_instance: '',
  green_api_api_token: '',
  smtp_host: '',
  smtp_port: '587',
  smtp_use_starttls: true,
  smtp_username: '',
  smtp_password: '',
  smtp_from_email: '',
  one_c_counterparty_id: '',
  one_c_name_match: '',
  one_c_login: '',
  one_c_password: '',
  one_c_base_url: '',
  one_c_basic_user: '',
  one_c_basic_password: '',
  nova_organization_id: '',
  ...novaScriptFormDefaults('com'),
  one_c_connection_mode: 'auto',
  xlsx_priority: 'disabled',
  xlsx_parser_key: '',
  portal_username: '',
  portal_password: '',
  invoice_iik: '',
  invoice_kbe: '',
  invoice_bank_name: '',
  invoice_bank_bik: '',
  invoice_payment_knp: '',
  invoice_executor_name: '',
  invoice_supplier_address: '',
  invoice_contract_text: 'Без договора',
  invoice_due_day: '5',
  invoice_due_day_utilities: '5',
  invoice_due_day_operations: '5',
  payment_rent_enabled: true,
  payment_utilities_enabled: true,
  payment_operations_enabled: true,
  stamp_file_path: '',
  signature_file_path: '',
  is_active: true,
}

/** Поля Nova/COM (org_id) — скрыты только в режиме OData напрямую. */
export function tenantShowsNovaComFields(mode: string): boolean {
  return mode !== 'odata_direct'
}

/** Поля OData — скрыты только в режиме Nova / MCP (COM). */
export function tenantShowsODataFields(mode: string): boolean {
  return mode !== 'nova_org'
}

export default function App() {
  const showToast = useToast()
  const { token, isSuper, loginError, loginLoading, login, logout } = useAdminSession()
  const [username, setUsername] = useState('super_metrix')
  const [password, setPassword] = useState('')
  const [activeTab, setActiveTab] = useState<TabKey>('trc')
  const [phoneRefreshKey, setPhoneRefreshKey] = useState(0)
  const [trcs, setTrcs] = useState<TRC[]>([])
  const [selectedTrcId, setSelectedTrcId] = useState<number | null>(() => {
    const raw = localStorage.getItem(SELECTED_TRC_KEY)
    return raw ? Number(raw) : null
  })
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [trcForm, setTrcForm] = useState(emptyTrcForm)
  const [editingTrc, setEditingTrc] = useState(false)
  const [trcFormOpen, setTrcFormOpen] = useState(false)
  const [trcSaveNotice, setTrcSaveNotice] = useState('')
  const [trcFormError, setTrcFormError] = useState('')
  const [tenantForm, setTenantForm] = useState({ ...emptyTenantForm })
  const [editingTenantId, setEditingTenantId] = useState<number | null>(null)
  const [tenantFormOpen, setTenantFormOpen] = useState(false)
  const [tenantSaveNotice, setTenantSaveNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const [tenantFormError, setTenantFormError] = useState('')
  const showNovaComFields = tenantShowsNovaComFields(tenantForm.one_c_connection_mode)
  const showODataFields = tenantShowsODataFields(tenantForm.one_c_connection_mode)
  const showNovaMcpSettings = tenantForm.one_c_connection_mode === 'nova_org'
  const odataFieldsMasked = tenantForm.one_c_connection_mode === 'nova_org'
  const [tenantsLoadError, setTenantsLoadError] = useState('')
  const [cpDirectory, setCpDirectory] = useState<CounterpartyDirectoryItem[]>([])
  const [cpDirectoryLoading, setCpDirectoryLoading] = useState(false)
  const [cpDirectoryError, setCpDirectoryError] = useState('')
  const [cpPhoneFilter, setCpPhoneFilter] = useState('')
  const [stampFile, setStampFile] = useState<File | null>(null)
  const [signatureFile, setSignatureFile] = useState<File | null>(null)
  const [tenantSavedSecrets, setTenantSavedSecrets] = useState({
    one_c_password: false,
    one_c_basic_password: false,
    green_api_api_token: false,
    smtp_password: false,
  })
  const [smtpTestNotice, setSmtpTestNotice] = useState('')
  const [smtpTestLoading, setSmtpTestLoading] = useState(false)
  const [novaResolveLoading, setNovaResolveLoading] = useState(false)
  const [novaResolveNotice, setNovaResolveNotice] = useState('')

  useEffect(() => {
    if (token) {
      loadTrcs()
    }
  }, [token])

  useEffect(() => {
    if (selectedTrcId) {
      localStorage.setItem(SELECTED_TRC_KEY, String(selectedTrcId))
      loadTenants(selectedTrcId)
      loadTrcForm(selectedTrcId)
    } else {
      localStorage.removeItem(SELECTED_TRC_KEY)
      setTenants([])
      setTrcForm(emptyTrcForm)
      setEditingTrc(false)
    }
  }, [selectedTrcId])

  const loadTrcForm = async (trcId: number) => {
    try {
      const trc = await adminApi.getTrc(trcId)
      setTrcForm({
        name: trc.name,
        phone: trc.phone || '',
        bin_value: trc.bin_value || '',
        iin_value: trc.iin_value || '',
        message_template: trc.message_template || defaultTrcTemplate,
        green_api_url: trc.green_api_url || '',
        green_api_media_url: trc.green_api_media_url || '',
        green_api_id_instance: trc.green_api_id_instance || '',
        green_api_api_token: trc.green_api_api_token || '',
        portal_username: trc.portal_username || '',
        portal_password: '',
        is_active: trc.is_active,
      })
      setEditingTrc(true)
    } catch {
      setTrcForm(emptyTrcForm)
      setEditingTrc(false)
    }
  }

  const loadTrcs = async () => {
    try {
      const data = await adminApi.listTrcs()
      setTrcs(data)
      const stillExists = selectedTrcId && data.some((t) => t.id === selectedTrcId)
      if (!stillExists && data.length > 0) {
        setSelectedTrcId(data[0].id)
      }
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number } }
      if (axiosErr.response?.status === 401) {
        logout()
      }
    }
  }

  const loadTenants = async (trcId: number) => {
    setTenantsLoadError('')
    try {
      const data = await adminApi.listTenants(trcId)
      setTenants(data)
    } catch (err: unknown) {
      setTenants([])
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      setTenantsLoadError(
        axiosErr.response?.data?.detail || 'Не удалось загрузить список арендаторов',
      )
    }
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    await login(username, password)
  }

  const handleSaveTrc = async () => {
    setTrcFormError('')
    if (!trcForm.name.trim()) {
      setTrcFormError('Укажите название ТРЦ')
      return
    }
    setLoading(true)
    try {
      const payload = {
        name: trcForm.name.trim(),
        phone: trcForm.phone.trim() || null,
        bin_value: trcForm.bin_value.trim() || null,
        iin_value: trcForm.iin_value.trim() || null,
        message_template: trcForm.message_template.trim() || null,
        green_api_url: trcForm.green_api_url.trim() || null,
        green_api_media_url: trcForm.green_api_media_url.trim() || null,
        green_api_id_instance: trcForm.green_api_id_instance.trim() || null,
        green_api_api_token: trcForm.green_api_api_token.trim() || undefined,
        is_active: trcForm.is_active,
      }
      const portalPayload =
        editingTrc && selectedTrcId
          ? {
              portal_username: trcForm.portal_username.trim() || undefined,
              portal_password: trcForm.portal_password.trim() || undefined,
            }
          : {}
      const wasEditing = Boolean(editingTrc && selectedTrcId)
      let savedName = trcForm.name.trim()
      if (wasEditing && selectedTrcId) {
        const saved = await adminApi.updateTrc(selectedTrcId, { ...payload, ...portalPayload })
        savedName = saved.name
        await loadTrcs()
        await loadTrcForm(selectedTrcId)
        await loadTenants(selectedTrcId)
      } else {
        const created = await adminApi.createTrc(payload)
        savedName = created.name
        setSelectedTrcId(created.id)
        await loadTrcs()
        await loadTrcForm(created.id)
      }
      setTrcSaveNotice(wasEditing ? 'ТРЦ сохранён' : `ТРЦ «${savedName}» добавлен`)
      setTrcFormOpen(false)
    } catch (err: unknown) {
      const axiosErr = err as {
        response?: { status?: number; data?: { detail?: unknown } }
        message?: string
      }
      if (!axiosErr.response) {
        setTrcFormError('Нет связи с API')
        return
      }
      const detail = axiosErr.response.data?.detail
      if (typeof detail === 'string') {
        setTrcFormError(detail)
      } else if (axiosErr.response.status === 401) {
        setTrcFormError('Сессия истекла. Войдите снова.')
      } else if (axiosErr.response.status && axiosErr.response.status >= 500) {
        setTrcFormError('Ошибка сервера. Проверьте, что API запущен и доступна база данных.')
      } else {
        setTrcFormError('Не удалось сохранить ТРЦ')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleSaveTenant = async () => {
    if (!selectedTrcId) return
    setTenantFormError('')
    if (!tenantForm.name.trim()) {
      setTenantFormError('Укажите название арендатора')
      return
    }
    if (!tenantForm.legal_name.trim()) {
      setTenantFormError('Укажите ИП / ТОО (юр. название)')
      return
    }
    setLoading(true)
    try {
      const dueDayValue = tenantForm.invoice_due_day.trim()
      const dueDayUtilitiesValue = tenantForm.invoice_due_day_utilities.trim()
      const dueDayOperationsValue = tenantForm.invoice_due_day_operations.trim()
      const dueDayParsed = dueDayValue ? Number(dueDayValue) : undefined
      const dueDayUtilitiesParsed = dueDayUtilitiesValue
        ? Number(dueDayUtilitiesValue)
        : undefined
      const dueDayOperationsParsed = dueDayOperationsValue
        ? Number(dueDayOperationsValue)
        : undefined
      if (
        dueDayParsed !== undefined &&
        (!Number.isInteger(dueDayParsed) || dueDayParsed < 1 || dueDayParsed > 31)
      ) {
        setTenantFormError('Срок оплаты аренды должен быть целым числом от 1 до 31')
        setLoading(false)
        return
      }
      if (
        dueDayUtilitiesParsed !== undefined &&
        (!Number.isInteger(dueDayUtilitiesParsed) ||
          dueDayUtilitiesParsed < 1 ||
          dueDayUtilitiesParsed > 31)
      ) {
        setTenantFormError('Срок оплаты коммуналки должен быть целым числом от 1 до 31')
        setLoading(false)
        return
      }
      if (
        dueDayOperationsParsed !== undefined &&
        (!Number.isInteger(dueDayOperationsParsed) ||
          dueDayOperationsParsed < 1 ||
          dueDayOperationsParsed > 31)
      ) {
        setTenantFormError(
          'Срок оплаты эксплуатации и маркетинга должен быть целым числом от 1 до 31',
        )
        setLoading(false)
        return
      }
      const payload = {
        name: tenantForm.name.trim(),
        legal_name: tenantForm.legal_name.trim(),
        org_type: tenantForm.org_type,
        bin_value: tenantForm.bin_value.trim() || null,
        iin_value: tenantForm.iin_value.trim() || null,
        phone: tenantForm.phone.trim() || null,
        message_template: tenantForm.message_template.trim() || null,
        green_api_url: tenantForm.green_api_url.trim() || null,
        green_api_media_url: tenantForm.green_api_media_url.trim() || null,
        green_api_id_instance: tenantForm.green_api_id_instance.trim() || null,
        one_c_counterparty_id: tenantForm.one_c_counterparty_id.trim() || null,
        one_c_name_match: tenantForm.one_c_name_match.trim() || null,
        one_c_base_url: tenantForm.one_c_base_url.trim() || null,
        one_c_basic_user: tenantForm.one_c_basic_user.trim() || null,
        nova_organization_id: tenantForm.nova_organization_id.trim()
          ? Number(tenantForm.nova_organization_id)
          : null,
        one_c_connection_mode: tenantForm.one_c_connection_mode || 'auto',
        xlsx_priority: tenantForm.xlsx_priority || 'disabled',
        xlsx_parser_key: tenantForm.xlsx_parser_key.trim() || null,
        portal_username: tenantForm.portal_username.trim() || undefined,
        invoice_iik: tenantForm.invoice_iik.trim() || null,
        invoice_kbe: tenantForm.invoice_kbe.trim() || null,
        invoice_bank_name: tenantForm.invoice_bank_name.trim() || null,
        invoice_bank_bik: tenantForm.invoice_bank_bik.trim() || null,
        invoice_payment_knp: tenantForm.invoice_payment_knp.trim() || null,
        invoice_executor_name: tenantForm.invoice_executor_name.trim() || null,
        invoice_supplier_address: tenantForm.invoice_supplier_address.trim() || null,
        invoice_contract_text: tenantForm.invoice_contract_text.trim() || null,
        invoice_due_day: dueDayParsed,
        invoice_due_day_utilities: dueDayUtilitiesParsed,
        invoice_due_day_operations: dueDayOperationsParsed,
        payment_rent_enabled: tenantForm.payment_rent_enabled,
        payment_utilities_enabled: tenantForm.payment_utilities_enabled,
        payment_operations_enabled: tenantForm.payment_operations_enabled,
        smtp_host: tenantForm.smtp_host.trim() || null,
        smtp_port: tenantForm.smtp_port.trim()
          ? Number(tenantForm.smtp_port)
          : null,
        smtp_use_starttls: tenantForm.smtp_use_starttls,
        smtp_username: tenantForm.smtp_username.trim() || null,
        smtp_from_email: tenantForm.smtp_from_email.trim() || null,
        is_active: tenantForm.is_active,
      }
      const portalPassword = tenantForm.portal_password.trim()
      if (portalPassword) {
        Object.assign(payload, { portal_password: portalPassword })
      }
      const oneCLogin = tenantForm.one_c_login.trim()
      const oneCPassword = tenantForm.one_c_password.trim()
      const oneCBasicPassword = tenantForm.one_c_basic_password.trim()
      const greenToken = tenantForm.green_api_api_token.trim()
      const smtpPassword = tenantForm.smtp_password.trim()
      if (smtpPassword) {
        Object.assign(payload, { smtp_password: smtpPassword })
      }
      const usesNovaOnly =
        tenantForm.one_c_connection_mode === 'nova_org' ||
        (tenantForm.one_c_connection_mode === 'auto' &&
          tenantForm.nova_organization_id.trim() &&
          !tenantForm.one_c_base_url.trim())
      if (tenantForm.one_c_connection_mode === 'nova_org') {
        payload.one_c_base_url = ''
        payload.one_c_basic_user = ''
        Object.assign(payload, {
          nova_mcp_system_type: tenantForm.nova_mcp_system_type || 'com',
          nova_script_invoices: parseNovaScriptId(tenantForm.nova_script_invoices),
          nova_script_payments: parseNovaScriptId(tenantForm.nova_script_payments),
          nova_script_counterparties: parseNovaScriptId(tenantForm.nova_script_counterparties),
          nova_script_balance: parseNovaScriptId(tenantForm.nova_script_balance),
          nova_script_invoice_by_id: parseNovaScriptId(tenantForm.nova_script_invoice_by_id),
        })
      }
      if (editingTenantId) {
        if (tenantForm.one_c_connection_mode === 'nova_org') {
          Object.assign(payload, { one_c_login: '' })
        } else if (oneCLogin) {
          Object.assign(payload, { one_c_login: oneCLogin })
        }
        if (oneCPassword) {
          Object.assign(payload, { one_c_password: oneCPassword })
        }
        if (oneCBasicPassword) {
          Object.assign(payload, { one_c_basic_password: oneCBasicPassword })
        }
        if (greenToken) {
          Object.assign(payload, { green_api_api_token: greenToken })
        }
      }
      const wasEditing = Boolean(editingTenantId)
      let saved: Tenant
      if (wasEditing && editingTenantId) {
        saved = await adminApi.updateTenant(selectedTrcId, editingTenantId, payload)
      } else {
        const createPayload: TenantCreatePayload = {
          ...payload,
          one_c_login: oneCLogin,
          one_c_password: usesNovaOnly ? oneCPassword || '' : oneCPassword,
          ...(oneCBasicPassword ? { one_c_basic_password: oneCBasicPassword } : {}),
          ...(greenToken ? { green_api_api_token: greenToken } : {}),
        }
        if (!usesNovaOnly && !oneCPassword) {
          setTenantFormError('Укажите пароль 1С или подключите Nova org_id (COM/MCP)')
          setLoading(false)
          return
        }
        saved = await adminApi.createTenant(selectedTrcId, createPayload)
      }
      const tenantId = saved.id
      setEditingTenantId(tenantId)
      if (stampFile) {
        saved = await adminApi.uploadTenantStamp(selectedTrcId, tenantId, stampFile)
      }
      if (signatureFile) {
        saved = await adminApi.uploadTenantSignature(selectedTrcId, tenantId, signatureFile)
      }
      await loadTenants(selectedTrcId)
      setTenantSaveNotice(
        wasEditing ? 'Арендатор сохранён' : `Арендатор «${saved.name}» добавлен`,
      )
      closeTenantForm()
    } catch (err: unknown) {
      const axiosErr = err as {
        response?: { status?: number; data?: { detail?: unknown } }
      }
      if (axiosErr.response?.status === 422) {
        const detail = axiosErr.response.data?.detail
        if (Array.isArray(detail)) {
          const msgs = detail.map((d: { loc?: string[]; msg?: string }) => {
            const field = d.loc?.slice(-1)[0] || 'поле'
            return `${field}: ${d.msg}`
          })
          setTenantFormError(msgs.join('; '))
        } else {
          setTenantFormError('Проверьте данные формы (ошибка валидации)')
        }
      } else {
        setTenantFormError('Не удалось сохранить арендатора')
      }
    } finally {
      setLoading(false)
    }
  }

  const uploadStampNow = async (file: File) => {
    if (!selectedTrcId || !editingTenantId) return
    setTenantFormError('')
    setLoading(true)
    try {
      const saved = await adminApi.uploadTenantStamp(selectedTrcId, editingTenantId, file)
      startEditTenant(saved)
      setStampFile(null)
      await loadTenants(selectedTrcId)
    } catch {
      setTenantFormError('Не удалось загрузить печать')
    } finally {
      setLoading(false)
    }
  }

  const uploadSignatureNow = async (file: File) => {
    if (!selectedTrcId || !editingTenantId) return
    setTenantFormError('')
    setLoading(true)
    try {
      const saved = await adminApi.uploadTenantSignature(selectedTrcId, editingTenantId, file)
      startEditTenant(saved)
      setSignatureFile(null)
      await loadTenants(selectedTrcId)
    } catch {
      setTenantFormError('Не удалось загрузить подпись')
    } finally {
      setLoading(false)
    }
  }

  const closeTenantForm = () => {
    setTenantFormOpen(false)
    setEditingTenantId(null)
    setTenantForm(emptyTenantForm)
    setStampFile(null)
    setSignatureFile(null)
    setTenantSavedSecrets({
      one_c_password: false,
      one_c_basic_password: false,
      green_api_api_token: false,
      smtp_password: false,
    })
    setNovaResolveNotice('')
    setSmtpTestNotice('')
  }

  const loadNovaOrg = async () => {
    const orgId = Number(tenantForm.nova_organization_id)
    if (!Number.isInteger(orgId) || orgId < 1) {
      setTenantFormError('Укажите корректный Nova org_id (целое число ≥ 1)')
      return
    }
    const userMode = tenantForm.one_c_connection_mode
    setNovaResolveLoading(true)
    setTenantFormError('')
    setNovaResolveNotice('')
    try {
      const res = await adminApi.resolveNovaOrg(orgId)
      setTenantForm((prev) => {
        const userWantsCom = userMode === 'nova_org'
        const userWantsOdata = userMode === 'odata_direct'
        const mode = userWantsCom
          ? 'nova_org'
          : userWantsOdata
            ? 'odata_direct'
            : res.connection_mode || prev.one_c_connection_mode
        const isCom = mode === 'nova_org'
        const mcpType = (res.nova_mcp_system_type as NovaMcpSystemType) || 'com'
        const scriptDefaults = NOVA_SCRIPT_DEFAULTS[mcpType]
        return {
          ...prev,
          nova_organization_id: String(orgId),
          one_c_connection_mode: mode,
          ...(isCom
            ? {
                one_c_base_url: '',
                one_c_login: '',
                one_c_basic_user: '',
                nova_mcp_system_type: mcpType,
                nova_script_invoices: String(
                  res.nova_script_invoices ?? scriptDefaults.nova_script_invoices,
                ),
                nova_script_payments: String(
                  res.nova_script_payments ?? scriptDefaults.nova_script_payments,
                ),
                nova_script_counterparties: String(
                  res.nova_script_counterparties ?? scriptDefaults.nova_script_counterparties,
                ),
                nova_script_balance: String(
                  res.nova_script_balance ?? scriptDefaults.nova_script_balance,
                ),
                nova_script_invoice_by_id: String(
                  res.nova_script_invoice_by_id ?? scriptDefaults.nova_script_invoice_by_id,
                ),
              }
            : {
                one_c_base_url: res.odata_url || prev.one_c_base_url,
                one_c_login: res.one_c_login || prev.one_c_login,
                one_c_basic_user: res.one_c_login || prev.one_c_basic_user,
              }),
        }
      })
      if (userMode === 'nova_org' && res.odata_url) {
        setNovaResolveNotice(
          `org_id ${orgId}: режим MCP mynova (${res.nova_mcp_system_type || 'odata'}). ` +
            `Скрипты org ${orgId}: ${res.nova_script_invoices ?? '—'}–${res.nova_script_invoice_by_id ?? '—'}. ` +
            (res.test_ok && res.counterparties_count != null
              ? `Проверка: ${res.counterparties_count} контрагентов.`
              : res.message)
        )
      } else if (userMode === 'nova_org') {
        setNovaResolveNotice(res.message)
      } else {
        setNovaResolveNotice(res.message)
      }
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null
      setTenantFormError(detail || 'Не удалось загрузить org_id из Nova')
    } finally {
      setNovaResolveLoading(false)
    }
  }

  const startEditTenant = (tenant: Tenant) => {
    setTenantFormOpen(true)
    setTenantSaveNotice('')
    setEditingTenantId(tenant.id)
    setTenantForm({
      name: tenant.name,
      legal_name: tenant.legal_name,
      org_type: tenant.org_type,
      bin_value: tenant.bin_value || '',
      iin_value: tenant.iin_value || '',
      phone: tenant.phone || '',
      message_template: tenant.message_template || defaultTenantTemplate,
      green_api_url: tenant.green_api_url || '',
      green_api_media_url: tenant.green_api_media_url || '',
      green_api_id_instance: tenant.green_api_id_instance || '',
      green_api_api_token: '',
      smtp_host: tenant.smtp_host || '',
      smtp_port: tenant.smtp_port ? String(tenant.smtp_port) : '587',
      smtp_use_starttls: tenant.smtp_use_starttls !== false,
      smtp_username: tenant.smtp_username || '',
      smtp_password: '',
      smtp_from_email: tenant.smtp_from_email || '',
      one_c_counterparty_id: tenant.one_c_counterparty_id || '',
      one_c_name_match: tenant.one_c_name_match || '',
      one_c_login: tenant.one_c_login,
      one_c_password: '',
      one_c_base_url: tenant.one_c_base_url || '',
      one_c_basic_user: tenant.one_c_basic_user || '',
      one_c_basic_password: '',
      nova_organization_id: tenant.nova_organization_id ? String(tenant.nova_organization_id) : '',
      one_c_connection_mode: tenant.one_c_connection_mode || 'auto',
      xlsx_priority: tenant.xlsx_priority || 'disabled',
      xlsx_parser_key: tenant.xlsx_parser_key || '',
      ...(tenant.one_c_connection_mode === 'nova_org'
        ? tenantNovaScriptFields(tenant)
        : novaScriptFormDefaults('com')),
      portal_username: tenant.portal_username || '',
      portal_password: '',
      invoice_iik: tenant.invoice_iik || '',
      invoice_kbe: tenant.invoice_kbe || '',
      invoice_bank_name: tenant.invoice_bank_name || '',
      invoice_bank_bik: tenant.invoice_bank_bik || '',
      invoice_payment_knp: tenant.invoice_payment_knp || '',
      invoice_executor_name: tenant.invoice_executor_name || '',
      invoice_supplier_address: tenant.invoice_supplier_address || '',
      invoice_contract_text: tenant.invoice_contract_text || 'Без договора',
      invoice_due_day: tenant.invoice_due_day ? String(tenant.invoice_due_day) : '5',
      invoice_due_day_utilities: tenant.invoice_due_day_utilities
        ? String(tenant.invoice_due_day_utilities)
        : '5',
      invoice_due_day_operations: tenant.invoice_due_day_operations
        ? String(tenant.invoice_due_day_operations)
        : '5',
      payment_rent_enabled: tenant.payment_rent_enabled !== false,
      payment_utilities_enabled: tenant.payment_utilities_enabled !== false,
      payment_operations_enabled: tenant.payment_operations_enabled !== false,
      stamp_file_path: tenant.stamp_file_path || '',
      signature_file_path: tenant.signature_file_path || '',
      is_active: tenant.is_active,
    })
    setStampFile(null)
    setSignatureFile(null)
    setTenantSavedSecrets({
      one_c_password: Boolean(tenant.has_one_c_password),
      one_c_basic_password: Boolean(tenant.has_one_c_basic_password),
      green_api_api_token: Boolean(tenant.has_green_api_api_token),
      smtp_password: Boolean(tenant.has_smtp_password),
    })
    setSmtpTestNotice('')
  }

  if (!token) {
    return (
      <div className="login-wrap">
        <form className="card login-card" onSubmit={handleLogin}>
          <h2>Вход в админку</h2>
          <div className="row" style={{ flexDirection: 'column' }}>
            <label>
              Логин
              <input value={username} onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label>
              Пароль
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <button className="btn-primary" type="submit" disabled={loginLoading}>
              Войти
            </button>
            {loginError && <div className="error">{loginError}</div>}
          </div>
        </form>
      </div>
    )
  }

  const selectedTrc = trcs.find((t) => t.id === selectedTrcId)

  const tabs: TabDef<TabKey>[] = [
    { key: 'trc', label: 'ТРЦ', icon: Building2 },
    { key: 'tenants', label: 'Арендаторы', icon: Users },
    { key: 'phonebook', label: 'Телефоны получателей', icon: Phone },
    { key: 'whatsapplog', label: 'Журнал WhatsApp', icon: MessageSquare },
    ...(isSuper ? [{ key: 'autonotify' as const, label: 'Авторассылка', icon: Send }] : []),
    ...(isSuper ? [{ key: 'adminusers' as const, label: 'Пользователи', icon: UserPlus }] : []),
  ]

  return (
    <div className="app">
      <div className="header">
        <h1>Админка ТРЦ</h1>
        <button
          className="btn-secondary"
          onClick={logout}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          <LogOut size={14} />
          Выйти
        </button>
      </div>

      <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

      {activeTab === 'trc' && (
      <div className="card">
        <h3>Торговые центры (ТРЦ) {editingTrc ? '— редактирование' : '— новый'}</h3>
        <div className="row" style={{ marginBottom: 12 }}>
          <label>
            Выбранный ТРЦ
            <select
              value={selectedTrcId ?? ''}
              onChange={(e) => setSelectedTrcId(Number(e.target.value))}
            >
              {trcs.map((trc) => (
                <option key={trc.id} value={trc.id}>
                  {trc.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn-secondary"
            onClick={() => {
              setTrcSaveNotice('')
              setTrcFormOpen(true)
              setSelectedTrcId(null)
              setTrcForm(emptyTrcForm)
              setEditingTrc(false)
            }}
          >
            + Новый ТРЦ
          </button>
          {selectedTrc && !trcFormOpen && (
            <button
              className="btn-secondary"
              onClick={() => {
                setTrcSaveNotice('')
                setTrcFormOpen(true)
              }}
            >
              Изменить ТРЦ
            </button>
          )}
          {selectedTrc && (
            <button
              className="btn-danger"
              onClick={async () => {
                if (!confirm(`Удалить ТРЦ «${selectedTrc.name}» и всех арендаторов?`)) return
                try {
                  await adminApi.deleteTrc(selectedTrc.id)
                  setSelectedTrcId(null)
                  setTrcForm(emptyTrcForm)
                  setEditingTrc(false)
                  await loadTrcs()
                  showToast('ТРЦ удалён', 'success')
                } catch (err: unknown) {
                  const axiosErr = err as { response?: { data?: { detail?: string } } }
                  showToast(axiosErr.response?.data?.detail || 'Не удалось удалить ТРЦ', 'error')
                }
              }}
            >
              Удалить ТРЦ
            </button>
          )}
        </div>
        {trcSaveNotice && !trcFormOpen && (
          <div
            style={{
              marginBottom: 12,
              padding: '10px 14px',
              borderRadius: 8,
              background: '#ecfdf5',
              color: '#15803d',
              fontSize: 14,
            }}
          >
            {trcSaveNotice}
          </div>
        )}
        {trcFormOpen && (
          <>
        <div className="grid-2">
          <label>
            Название ТРЦ
            <input
              value={trcForm.name}
              onChange={(e) => setTrcForm({ ...trcForm, name: e.target.value })}
              placeholder="Ритц-Палас"
            />
          </label>
          <label>
            Телефон WhatsApp ТРЦ
            <input
              value={trcForm.phone}
              onChange={(e) => setTrcForm({ ...trcForm, phone: e.target.value })}
              placeholder="+77001234567"
            />
          </label>
          <label>
            БИН
            <input
              value={trcForm.bin_value}
              onChange={(e) => setTrcForm({ ...trcForm, bin_value: e.target.value })}
            />
          </label>
          <label>
            ИИН
            <input
              value={trcForm.iin_value}
              onChange={(e) => setTrcForm({ ...trcForm, iin_value: e.target.value })}
            />
          </label>
          <label style={{ gridColumn: '1 / -1' }}>
            Шаблон сообщения ({'{trc_name}'}, {'{tenant_name}'}, {'{counterparty_name}'}, {'{details}'}, {'{invoice_number}'})
            <textarea
              rows={6}
              value={trcForm.message_template}
              onChange={(e) => setTrcForm({ ...trcForm, message_template: e.target.value })}
              style={{ width: '100%', borderRadius: 8, padding: 8, border: '1px solid #d1d5db' }}
            />
          </label>
          <label>
            Green API URL
            <input
              value={trcForm.green_api_url}
              onChange={(e) => setTrcForm({ ...trcForm, green_api_url: e.target.value })}
            />
          </label>
          <label>
            Green API Media URL
            <input
              value={trcForm.green_api_media_url}
              onChange={(e) => setTrcForm({ ...trcForm, green_api_media_url: e.target.value })}
            />
          </label>
          <label>
            Green API idInstance
            <input
              value={trcForm.green_api_id_instance}
              onChange={(e) =>
                setTrcForm({ ...trcForm, green_api_id_instance: e.target.value })
              }
            />
          </label>
          <label>
            Green API apiTokenInstance
            <input
              type="password"
              value={trcForm.green_api_api_token}
              onChange={(e) =>
                setTrcForm({ ...trcForm, green_api_api_token: e.target.value })
              }
            />
          </label>
          <label>
            Логин на сайт (портал ТРЦ)
            <input
              value={trcForm.portal_username}
              onChange={(e) =>
                setTrcForm({ ...trcForm, portal_username: e.target.value })
              }
              placeholder="логин для входа на основной сайт от имени ТРЦ"
              autoComplete="off"
            />
          </label>
          <label>
            Пароль на сайт (оставьте пустым, чтобы не менять)
            <input
              type="password"
              value={trcForm.portal_password}
              onChange={(e) =>
                setTrcForm({ ...trcForm, portal_password: e.target.value })
              }
              autoComplete="new-password"
            />
          </label>
        </div>
        {trcFormError && <div className="error">{trcFormError}</div>}
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn-primary" onClick={handleSaveTrc} disabled={loading}>
            {editingTrc && selectedTrcId ? 'Сохранить ТРЦ' : 'Добавить ТРЦ'}
          </button>
        </div>
        <p style={{ fontSize: 12, color: '#6b7280', marginTop: 8 }}>
          Счета арендаторам отправляются через Green API этого ТРЦ (номер WhatsApp ТРЦ).
        </p>
          </>
        )}
      </div>
      )}

      {activeTab !== 'trc' && activeTab !== 'autonotify' && activeTab !== 'adminusers' && !selectedTrcId && (
        <div className="card">
          <p style={{ fontSize: 14, color: '#6b7280', margin: 0 }}>
            Сначала выберите ТРЦ на вкладке «ТРЦ».
          </p>
        </div>
      )}

      {activeTab === 'tenants' && selectedTrcId && (
        <>
          <DebtSummaryCard trcId={selectedTrcId} />
          <div className="card">
            <h3>Арендаторы: {selectedTrc?.name}</h3>
            {tenantSaveNotice && !tenantFormOpen && (
              <div
                style={{
                  marginBottom: 12,
                  padding: '10px 14px',
                  borderRadius: 8,
                  background: '#ecfdf5',
                  color: '#15803d',
                  fontSize: 14,
                }}
              >
                {tenantSaveNotice}
              </div>
            )}
            <div className="row" style={{ marginBottom: 12 }}>
              <button
                className="btn-secondary"
                onClick={() => {
                  setTenantSaveNotice('')
                  setTenantFormOpen(true)
                  setEditingTenantId(null)
                  setTenantForm(emptyTenantForm)
                  setStampFile(null)
                  setSignatureFile(null)
                  setTenantSavedSecrets({
                    one_c_password: false,
                    one_c_basic_password: false,
                    green_api_api_token: false,
                    smtp_password: false,
                  })
                  setSmtpTestNotice('')
                }}
              >
                + Новый арендатор
              </button>
            </div>
            {tenantFormOpen && (
              <>
            <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 12px' }}>
              {editingTenantId ? 'Редактирование арендатора' : 'Новый арендатор'}
            </p>
            <div className="grid-2">
              <label>
                Название арендатора
                <input
                  value={tenantForm.name}
                  onChange={(e) => setTenantForm({ ...tenantForm, name: e.target.value })}
                />
              </label>
              <label>
                ИП / ТОО (юр. название)
                <input
                  value={tenantForm.legal_name}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, legal_name: e.target.value })
                  }
                />
              </label>
              <label>
                Тип
                <select
                  value={tenantForm.org_type}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, org_type: e.target.value })
                  }
                >
                  <option value="IP">ИП</option>
                  <option value="TOO">ТОО</option>
                </select>
              </label>
              <label>
                БИН
                <input
                  value={tenantForm.bin_value}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, bin_value: e.target.value })
                  }
                />
              </label>
              <label>
                ИИН
                <input
                  value={tenantForm.iin_value}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, iin_value: e.target.value })
                  }
                />
              </label>
              <label>
                Номер WhatsApp отправителя (для справки)
                <input
                  value={tenantForm.phone}
                  onChange={(e) => setTenantForm({ ...tenantForm, phone: e.target.value })}
                  placeholder="+77789750540"
                />
              </label>
              <label style={{ gridColumn: '1 / -1' }}>
                Шаблон сообщения для рассылки (в подписи обычно {'{tenant_name}'} — ИП/ТОО
                арендатора; {'{trc_name}'} — название ТРЦ; также {'{counterparty_name}'},{' '}
                {'{details}'}, {'{invoice_number}'})
                <textarea
                  rows={6}
                  value={tenantForm.message_template}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, message_template: e.target.value })
                  }
                  style={{
                    width: '100%',
                    borderRadius: 8,
                    padding: 8,
                    border: '1px solid #d1d5db',
                  }}
                />
              </label>
              <label>
                Green API idInstance (WhatsApp этого арендатора)
                <input
                  value={tenantForm.green_api_id_instance}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, green_api_id_instance: e.target.value })
                  }
                  placeholder="из console.green-api.com"
                />
              </label>
              <label>
                Green API apiTokenInstance
                <input
                  type="password"
                  value={tenantForm.green_api_api_token}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, green_api_api_token: e.target.value })
                  }
                  placeholder={
                    editingTenantId && tenantSavedSecrets.green_api_api_token
                      ? 'Сохранён в базе — введите только чтобы сменить'
                      : undefined
                  }
                  autoComplete="new-password"
                />
                {editingTenantId &&
                  tenantSavedSecrets.green_api_api_token &&
                  !tenantForm.green_api_api_token && (
                    <div style={{ fontSize: 12, marginTop: 6, color: '#15803d' }}>
                      Токен Green API сохранён в базе
                    </div>
                  )}
              </label>
              <label>
                Green API URL (опционально)
                <input
                  value={tenantForm.green_api_url}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, green_api_url: e.target.value })
                  }
                  placeholder="https://7107.api.greenapi.com"
                />
              </label>
              <div
                style={{
                  gridColumn: '1 / -1',
                  marginTop: 8,
                  padding: 16,
                  borderRadius: 8,
                  background: '#f8fafc',
                  border: '1px solid #e2e8f0',
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 8 }}>
                  SMTP (email-рассылка)
                </div>
                <div style={{ fontSize: 13, color: '#64748b', marginBottom: 12 }}>
                  Для Maxi Mall: smtp.cloud24.kz, порт 587, STARTTLS. У остальных можно оставить
                  пустым.
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 12,
                  }}
                >
                  <label>
                    SMTP host
                    <input
                      value={tenantForm.smtp_host}
                      onChange={(e) =>
                        setTenantForm({ ...tenantForm, smtp_host: e.target.value })
                      }
                      placeholder="smtp.cloud24.kz"
                    />
                  </label>
                  <label>
                    SMTP port
                    <input
                      value={tenantForm.smtp_port}
                      onChange={(e) =>
                        setTenantForm({ ...tenantForm, smtp_port: e.target.value })
                      }
                      placeholder="587"
                      inputMode="numeric"
                    />
                  </label>
                  <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input
                      type="checkbox"
                      checked={tenantForm.smtp_use_starttls}
                      onChange={(e) =>
                        setTenantForm({
                          ...tenantForm,
                          smtp_use_starttls: e.target.checked,
                        })
                      }
                    />
                    STARTTLS
                  </label>
                  <label>
                    From / email
                    <input
                      value={tenantForm.smtp_from_email}
                      onChange={(e) =>
                        setTenantForm({ ...tenantForm, smtp_from_email: e.target.value })
                      }
                      placeholder="noreply@maximall.kz"
                    />
                  </label>
                  <label>
                    SMTP login
                    <input
                      value={tenantForm.smtp_username}
                      onChange={(e) =>
                        setTenantForm({ ...tenantForm, smtp_username: e.target.value })
                      }
                      placeholder="noreply@maximall.kz"
                      autoComplete="off"
                    />
                  </label>
                  <label>
                    SMTP password
                    <input
                      type="password"
                      value={tenantForm.smtp_password}
                      onChange={(e) =>
                        setTenantForm({ ...tenantForm, smtp_password: e.target.value })
                      }
                      placeholder={
                        editingTenantId && tenantSavedSecrets.smtp_password
                          ? 'Сохранён в базе — введите только чтобы сменить'
                          : undefined
                      }
                      autoComplete="new-password"
                    />
                    {editingTenantId &&
                      tenantSavedSecrets.smtp_password &&
                      !tenantForm.smtp_password && (
                        <div style={{ fontSize: 12, marginTop: 6, color: '#15803d' }}>
                          SMTP пароль сохранён в базе
                        </div>
                      )}
                  </label>
                </div>
                <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    disabled={smtpTestLoading || loading || !editingTenantId}
                    onClick={async () => {
                      if (!selectedTrcId || !editingTenantId) {
                        setSmtpTestNotice('Сначала сохраните арендатора, затем проверьте SMTP')
                        return
                      }
                      setSmtpTestLoading(true)
                      setSmtpTestNotice('')
                      try {
                        const res = await adminApi.testTenantSmtp(selectedTrcId, editingTenantId, {
                          smtp_host: tenantForm.smtp_host.trim() || undefined,
                          smtp_port: tenantForm.smtp_port.trim()
                            ? Number(tenantForm.smtp_port)
                            : undefined,
                          smtp_use_starttls: tenantForm.smtp_use_starttls,
                          smtp_username: tenantForm.smtp_username.trim() || undefined,
                          smtp_password: tenantForm.smtp_password.trim() || undefined,
                          smtp_from_email: tenantForm.smtp_from_email.trim() || undefined,
                        })
                        setSmtpTestNotice(
                          res.ok
                            ? res.message || 'SMTP OK'
                            : res.error || 'SMTP проверка не прошла',
                        )
                      } catch (err: unknown) {
                        const detail =
                          err && typeof err === 'object' && 'response' in err
                            ? (err as { response?: { data?: { detail?: string } } }).response
                                ?.data?.detail
                            : null
                        setSmtpTestNotice(detail || 'Не удалось проверить SMTP')
                      } finally {
                        setSmtpTestLoading(false)
                      }
                    }}
                  >
                    {smtpTestLoading ? 'Проверка…' : 'Проверить SMTP'}
                  </button>
                  {!editingTenantId && (
                    <span style={{ fontSize: 13, color: '#64748b', alignSelf: 'center' }}>
                      Сохраните арендатора, чтобы проверить связь
                    </span>
                  )}
                </div>
                {smtpTestNotice && (
                  <div
                    style={{
                      marginTop: 10,
                      fontSize: 13,
                      color: smtpTestNotice.toLowerCase().includes('ok')
                        ? '#15803d'
                        : '#b45309',
                    }}
                  >
                    {smtpTestNotice}
                  </div>
                )}
              </div>
              <label>
                Фрагмент названия в 1С (например MOON)
                <input
                  value={tenantForm.one_c_name_match}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, one_c_name_match: e.target.value })
                  }
                />
              </label>
              <label>
                ID контрагента в 1С (GUID, опционально)
                <input
                  value={tenantForm.one_c_counterparty_id}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, one_c_counterparty_id: e.target.value })
                  }
                />
              </label>
              <label>
                Логин на сайт (портал арендатора)
                <input
                  value={tenantForm.portal_username}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, portal_username: e.target.value })
                  }
                  placeholder="уникальный логин для входа на основной сайт"
                  autoComplete="off"
                />
              </label>
              <label>
                Пароль на сайт (оставьте пустым, чтобы не менять)
                <input
                  type="password"
                  value={tenantForm.portal_password}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, portal_password: e.target.value })
                  }
                  autoComplete="new-password"
                />
              </label>
              <p style={{ gridColumn: '1 / -1', fontSize: 13, color: '#6b7280', margin: 0 }}>
                Реквизиты счёта на PDF берутся из 1С автоматически. Поля ниже — запасной вариант
                на случай, если в 1С у организации не заполнен основной банковский счёт: пусты — берём из 1С,
                заполнены — берём отсюда.
              </p>
              <label>
                ИИК для счёта
                <input
                  value={tenantForm.invoice_iik}
                  onChange={(e) => setTenantForm({ ...tenantForm, invoice_iik: e.target.value })}
                  placeholder="KZ..."
                />
              </label>
              <label>
                Кбе
                <input
                  value={tenantForm.invoice_kbe}
                  onChange={(e) => setTenantForm({ ...tenantForm, invoice_kbe: e.target.value })}
                  placeholder="19"
                />
              </label>
              <label>
                Банк бенефициара
                <input
                  value={tenantForm.invoice_bank_name}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, invoice_bank_name: e.target.value })
                  }
                />
              </label>
              <label>
                БИК банка
                <input
                  value={tenantForm.invoice_bank_bik}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, invoice_bank_bik: e.target.value })
                  }
                />
              </label>
              <label>
                Код назначения платежа (КНП)
                <input
                  value={tenantForm.invoice_payment_knp}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, invoice_payment_knp: e.target.value })
                  }
                />
              </label>
              <label>
                Исполнитель в счёте (подпись)
                <input
                  value={tenantForm.invoice_executor_name}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, invoice_executor_name: e.target.value })
                  }
                  placeholder="/Иванов И.И./"
                />
              </label>
              <label>
                Договор в счёте
                <input
                  value={tenantForm.invoice_contract_text}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, invoice_contract_text: e.target.value })
                  }
                />
              </label>
              <label style={{ gridColumn: '1 / -1' }}>
                Поставщик (адрес и реквизиты)
                <textarea
                  rows={2}
                  value={tenantForm.invoice_supplier_address}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, invoice_supplier_address: e.target.value })
                  }
                  style={{
                    width: '100%',
                    borderRadius: 8,
                    padding: 8,
                    border: '1px solid #d1d5db',
                  }}
                />
              </label>
              <p style={{ gridColumn: '1 / -1', fontSize: 13, color: '#6b7280', margin: '0 0 4px' }}>
                Виды оплат в портале арендатора. Снимите галочку, чтобы скрыть тип у арендатора.
              </p>
              <label>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <input
                    type="checkbox"
                    checked={tenantForm.payment_rent_enabled}
                    onChange={(e) =>
                      setTenantForm({ ...tenantForm, payment_rent_enabled: e.target.checked })
                    }
                  />
                  Срок оплаты аренды (день месяца, 1-31)
                </span>
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={tenantForm.invoice_due_day}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, invoice_due_day: e.target.value })
                  }
                  placeholder="5"
                  disabled={!tenantForm.payment_rent_enabled}
                />
              </label>
              <label>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <input
                    type="checkbox"
                    checked={tenantForm.payment_utilities_enabled}
                    onChange={(e) =>
                      setTenantForm({ ...tenantForm, payment_utilities_enabled: e.target.checked })
                    }
                  />
                  Срок оплаты коммуналки (день месяца, 1-31)
                </span>
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={tenantForm.invoice_due_day_utilities}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, invoice_due_day_utilities: e.target.value })
                  }
                  placeholder="5"
                  disabled={!tenantForm.payment_utilities_enabled}
                />
              </label>
              <label>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <input
                    type="checkbox"
                    checked={tenantForm.payment_operations_enabled}
                    onChange={(e) =>
                      setTenantForm({
                        ...tenantForm,
                        payment_operations_enabled: e.target.checked,
                      })
                    }
                  />
                  Срок оплаты эксплуатации и маркетинга (день месяца, 1-31)
                </span>
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={tenantForm.invoice_due_day_operations}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, invoice_due_day_operations: e.target.value })
                  }
                  placeholder="5"
                  disabled={!tenantForm.payment_operations_enabled}
                />
              </label>
              <div
                style={{
                  gridColumn: '1 / -1',
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: 16,
                }}
              >
                <label>
                  Печать арендатора (PNG/SVG)
                  <input
                    type="file"
                    accept=".png,.svg,image/png,image/svg+xml"
                    onChange={(e) => {
                      const file = e.target.files?.[0] || null
                      setStampFile(file)
                      if (file && editingTenantId) {
                        void uploadStampNow(file)
                      }
                    }}
                  />
                  {tenantForm.stamp_file_path ? (
                    <div style={{ fontSize: 12, marginTop: 6, color: '#15803d' }}>
                      Печать загружена на сервер
                    </div>
                  ) : stampFile && !editingTenantId ? (
                    <div style={{ fontSize: 12, marginTop: 6, color: '#b45309' }}>
                      Файл выбран — сначала сохраните арендатора, затем загрузится печать
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, marginTop: 6, color: '#6b7280' }}>
                      Печать не загружена
                    </div>
                  )}
                </label>
                <label>
                  Подпись (PNG/SVG)
                  <input
                    type="file"
                    accept=".png,.svg,image/png,image/svg+xml"
                    onChange={(e) => {
                      const file = e.target.files?.[0] || null
                      setSignatureFile(file)
                      if (file && editingTenantId) {
                        void uploadSignatureNow(file)
                      }
                    }}
                  />
                  {tenantForm.signature_file_path ? (
                    <div style={{ fontSize: 12, marginTop: 6, color: '#15803d' }}>
                      Подпись загружена на сервер
                    </div>
                  ) : signatureFile && !editingTenantId ? (
                    <div style={{ fontSize: 12, marginTop: 6, color: '#b45309' }}>
                      Файл выбран — сначала сохраните арендатора, затем загрузится подпись
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, marginTop: 6, color: '#6b7280' }}>
                      Подпись не загружена
                    </div>
                  )}
                </label>
              </div>
              <label style={{ gridColumn: '1 / -1' }}>
                Режим 1С
                <select
                  value={tenantForm.one_c_connection_mode}
                  onChange={(e) => {
                    const mode = e.target.value
                    setTenantForm((prev) => ({
                      ...prev,
                      one_c_connection_mode: mode,
                      ...(mode === 'nova_org'
                        ? {
                            one_c_base_url: '',
                            one_c_login: '',
                            one_c_basic_user: '',
                            // Keep already entered / saved script ids — do not reset to 11–20.
                            nova_mcp_system_type: prev.nova_mcp_system_type || 'com',
                          }
                        : {}),
                    }))
                    if (mode === 'nova_org') {
                      setNovaResolveNotice('')
                    }
                  }}
                >
                  <option value="auto">Авто (по URL / org_id)</option>
                  <option value="odata_direct">OData напрямую</option>
                  <option value="nova_org">MCP mynova</option>
                </select>
              </label>
              <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap', border: '1px dashed #d1d5db', borderRadius: 6, padding: 10 }}>
                <label style={{ flex: '1 1 260px' }}>
                  Загрузка Excel как источника данных
                  <select
                    value={tenantForm.xlsx_priority}
                    onChange={(e) => setTenantForm({ ...tenantForm, xlsx_priority: e.target.value })}
                  >
                    <option value="disabled">Выключено (по умолчанию)</option>
                    <option value="fallback_on_1c_failure">Фоллбэк — только если 1С недоступна/не отвечает</option>
                    <option value="prefer_xlsx">Excel — источник истины (побеждает 1С на показе)</option>
                  </select>
                </label>
                <label style={{ flex: '1 1 220px' }}>
                  Парсер файла (xlsx_parser_key)
                  <input
                    value={tenantForm.xlsx_parser_key}
                    onChange={(e) => setTenantForm({ ...tenantForm, xlsx_parser_key: e.target.value })}
                    placeholder="напр. maxi_mall"
                  />
                </label>
                {tenantForm.xlsx_priority !== 'disabled' && !tenantForm.xlsx_parser_key.trim() && (
                  <div style={{ flexBasis: '100%', fontSize: 12, color: '#b45309' }}>
                    ⚠️ Приоритет включён, но парсер не указан — загрузка файла у арендатора будет
                    падать с ошибкой. Кнопка загрузки в личном кабинете арендатора всё равно не
                    появится, пока оба поля не заполнены.
                  </div>
                )}
              </div>
              {showNovaComFields && (
              <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
                <label style={{ flex: '1 1 200px' }}>
                  Nova org_id
                  <input
                    value={tenantForm.nova_organization_id}
                    onChange={(e) =>
                      setTenantForm({ ...tenantForm, nova_organization_id: e.target.value })
                    }
                    placeholder="118 CityMall, 119 Maxi Mall"
                    inputMode="numeric"
                  />
                </label>
                <button
                  type="button"
                  onClick={loadNovaOrg}
                  disabled={novaResolveLoading || loading}
                  style={{ marginBottom: 2 }}
                >
                  {novaResolveLoading ? 'Загрузка…' : 'Загрузить из Nova'}
                </button>
              </div>
              )}
              {showNovaMcpSettings && (
                <div
                  style={{
                    gridColumn: '1 / -1',
                    padding: 16,
                    borderRadius: 8,
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                  }}
                >
                  <div style={{ fontWeight: 600, marginBottom: 12 }}>
                    Тип системы (для MCP mynova)
                  </div>
                  <div style={{ display: 'flex', gap: 24, marginBottom: 16, flexWrap: 'wrap' }}>
                    <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <input
                        type="radio"
                        name="nova_mcp_system_type"
                        checked={tenantForm.nova_mcp_system_type === 'odata'}
                        onChange={() =>
                          setTenantForm((prev) => ({
                            ...prev,
                            ...novaScriptFormDefaults('odata'),
                          }))
                        }
                      />
                      oData подключение
                    </label>
                    <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <input
                        type="radio"
                        name="nova_mcp_system_type"
                        checked={tenantForm.nova_mcp_system_type === 'com'}
                        onChange={() =>
                          setTenantForm((prev) => ({
                            ...prev,
                            ...novaScriptFormDefaults('com'),
                          }))
                        }
                      />
                      COM подключение
                    </label>
                    <button
                      type="button"
                      onClick={() =>
                        setTenantForm((prev) => ({
                          ...prev,
                          ...novaScriptFormDefaults(prev.nova_mcp_system_type || 'com'),
                        }))
                      }
                      style={{ marginLeft: 'auto' }}
                      title="Подставить дефолты для текущего типа: oData 11–15, COM 16–20"
                    >
                      Дефолтные скрипты
                    </button>
                  </div>
                  <div style={{ fontWeight: 600, marginBottom: 12 }}>
                    Скрипты (идентификаторы запросов)
                  </div>
                  <div style={{ display: 'grid', gap: 10 }}>
                    {(
                      [
                        ['nova_script_invoices', 'script_invoices', 'Получение списка счетов'],
                        ['nova_script_payments', 'script_payments', 'Получение платежей'],
                        [
                          'nova_script_counterparties',
                          'script_counterparties',
                          'Получение контрагентов',
                        ],
                        ['nova_script_balance', 'script_balance', 'Получение баланса'],
                        [
                          'nova_script_invoice_by_id',
                          'script_invoice_by_id',
                          'Получение счета по ID',
                        ],
                      ] as const
                    ).map(([field, label, hint]) => (
                      <label key={field} style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12 }}>
                        <span>{label}</span>
                        <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                          <input
                            value={tenantForm[field]}
                            onChange={(e) =>
                              setTenantForm({ ...tenantForm, [field]: e.target.value })
                            }
                            inputMode="numeric"
                          />
                          <span style={{ fontSize: 12, color: '#6b7280' }}>{hint}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                  <div
                    style={{
                      marginTop: 16,
                      padding: 12,
                      borderRadius: 8,
                      background: '#fffbeb',
                      border: '1px solid #fde68a',
                      fontSize: 13,
                    }}
                  >
                    <strong>Значения по умолчанию:</strong> oData — 11, 12, 13, 14, 15; COM — 16, 17,
                    18, 19, 20. Поля можно изменить вручную для отдельного ТРЦ.
                  </div>
                </div>
              )}
              {novaResolveNotice && (
                <div style={{ gridColumn: '1 / -1', fontSize: 12, color: '#15803d' }}>
                  {novaResolveNotice}
                </div>
              )}
              {showODataFields && (
                <>
              <label>
                Логин 1С (опционально, для выгрузки)
                <input
                  value={odataFieldsMasked ? '' : tenantForm.one_c_login}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, one_c_login: e.target.value })
                  }
                  placeholder={odataFieldsMasked ? 'Не используется в режиме COM' : undefined}
                />
              </label>
              <label>
                Пароль 1С
                <input
                  type="password"
                  value={odataFieldsMasked ? '' : tenantForm.one_c_password}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, one_c_password: e.target.value })
                  }
                  placeholder={
                    odataFieldsMasked
                      ? 'Не используется в режиме COM'
                      : editingTenantId && tenantSavedSecrets.one_c_password
                        ? 'Сохранён в базе — введите только чтобы сменить'
                        : 'Пароль OData / REST 1С'
                  }
                  autoComplete="new-password"
                />
                {!odataFieldsMasked &&
                  editingTenantId &&
                  tenantSavedSecrets.one_c_password &&
                  !tenantForm.one_c_password && (
                  <div style={{ fontSize: 12, marginTop: 6, color: '#15803d' }}>
                    Пароль 1С сохранён в базе
                  </div>
                )}
              </label>
              <label>
                URL 1С (опционально)
                <input
                  value={odataFieldsMasked ? '' : tenantForm.one_c_base_url}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, one_c_base_url: e.target.value })
                  }
                  placeholder={odataFieldsMasked ? 'Не используется в режиме COM' : undefined}
                />
              </label>
              <label>
                Basic user 1С (опционально)
                <input
                  value={odataFieldsMasked ? '' : tenantForm.one_c_basic_user}
                  onChange={(e) =>
                    setTenantForm({ ...tenantForm, one_c_basic_user: e.target.value })
                  }
                  placeholder={odataFieldsMasked ? 'Не используется в режиме COM' : undefined}
                />
              </label>
              <label>
                Basic password 1С (опционально)
                <input
                  type="password"
                  value={odataFieldsMasked ? '' : tenantForm.one_c_basic_password}
                  onChange={(e) =>
                    setTenantForm({
                      ...tenantForm,
                      one_c_basic_password: e.target.value,
                    })
                  }
                  placeholder={
                    odataFieldsMasked
                      ? 'Не используется в режиме COM'
                      : editingTenantId && tenantSavedSecrets.one_c_basic_password
                        ? 'Сохранён в базе — введите только чтобы сменить'
                        : undefined
                  }
                  autoComplete="new-password"
                />
                {!odataFieldsMasked &&
                  editingTenantId &&
                  tenantSavedSecrets.one_c_basic_password &&
                  !tenantForm.one_c_basic_password && (
                    <div style={{ fontSize: 12, marginTop: 6, color: '#15803d' }}>
                      Basic-пароль 1С сохранён в базе
                    </div>
                  )}
              </label>
                </>
              )}
            </div>
            <p style={{ fontSize: 12, color: '#6b7280', marginTop: 8 }}>
              Логин 1С, пароли и токены хранятся в базе. При сохранении пустое поле пароля не
              затирает уже сохранённое значение.
              {odataFieldsMasked &&
                ' В режиме COM поля OData остаются пустыми — подключение идёт через Nova org_id.'}
            </p>
            <p style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
              Текст рассылки берётся из <strong>шаблона арендатора</strong> (если пусто — из шаблона ТРЦ).
              WhatsApp отправляется с <strong>idInstance</strong> арендатора в Green API.
            </p>
            {tenantFormError && (
              <div className="error" style={{ marginTop: 12 }}>
                {tenantFormError}
              </div>
            )}
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn-primary" onClick={handleSaveTenant} disabled={loading}>
                {editingTenantId ? 'Сохранить' : 'Добавить арендатора'}
              </button>
              {editingTenantId && tenantForm.stamp_file_path && (
                <button
                  className="btn-danger"
                  onClick={async () => {
                    if (!selectedTrcId || !editingTenantId) return
                    await adminApi.removeTenantStamp(selectedTrcId, editingTenantId)
                    setTenantForm({ ...tenantForm, stamp_file_path: '' })
                    await loadTenants(selectedTrcId)
                  }}
                >
                  Удалить печать
                </button>
              )}
              {editingTenantId && tenantForm.signature_file_path && (
                <button
                  className="btn-danger"
                  onClick={async () => {
                    if (!selectedTrcId || !editingTenantId) return
                    await adminApi.removeTenantSignature(selectedTrcId, editingTenantId)
                    setTenantForm({ ...tenantForm, signature_file_path: '' })
                    await loadTenants(selectedTrcId)
                  }}
                >
                  Удалить подпись
                </button>
              )}
              {editingTenantId && (
                <button
                  className="btn-secondary"
                  onClick={() => {
                    closeTenantForm()
                  }}
                >
                  Отмена
                </button>
              )}
            </div>
              </>
            )}
          </div>
        </>
      )}

      {activeTab === 'phonebook' && selectedTrcId && (
        <>
          <div className="card">
            <h3>Телефоны контрагентов для WhatsApp (получатели отчётов)</h3>
            <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
              Для арендаторов с прямым подключением к 1С (OData) телефон подтягивается из карточки
              контрагента автоматически — это лишь подсказка. Для арендаторов через MCP mynova (COM)
              1С телефон не отдаёт вообще — вводите вручную. В любом случае значение из этой таблицы
              главнее: загрузите список контрагентов из 1С и укажите/поправьте номер, на который уходят
              счета и отчёты — сохранённое здесь не перезаписывается автоматически. Отправка идёт с
              номера ТРЦ (Green API).
            </p>
            <div className="row" style={{ marginBottom: 12, gap: 8, flexWrap: 'wrap' }}>
              <button
                className="btn-secondary"
                disabled={cpDirectoryLoading || tenants.length === 0}
                onClick={async () => {
                  if (!selectedTrcId) return
                  setCpDirectoryLoading(true)
                  setCpDirectoryError('')
                  try {
                    const tenantId = editingTenantId || tenants[0]?.id
                    const list = await adminApi.loadCounterpartyDirectory(
                      selectedTrcId,
                      tenantId,
                    )
                    setCpDirectory(list)
                  } catch {
                    setCpDirectoryError('Не удалось загрузить контрагентов из 1С')
                  } finally {
                    setCpDirectoryLoading(false)
                  }
                }}
              >
                {cpDirectoryLoading ? 'Загрузка…' : 'Загрузить контрагентов из 1С'}
              </button>
              <button
                className="btn-secondary"
                disabled={cpDirectoryLoading || tenants.length === 0}
                title="Для арендаторов без 1С вообще — контрагенты из последней загруженной xlsx-загрузки"
                onClick={async () => {
                  if (!selectedTrcId) return
                  const tenantId = editingTenantId || tenants[0]?.id
                  if (!tenantId) return
                  setCpDirectoryLoading(true)
                  setCpDirectoryError('')
                  try {
                    const list = await adminApi.loadCounterpartyDirectoryXlsx(
                      selectedTrcId,
                      tenantId,
                    )
                    setCpDirectory(list)
                    if (list.length === 0) {
                      setCpDirectoryError(
                        'Контрагентов из xlsx не найдено — у этого арендатора ещё не было загрузки, либо xlsx_parser_key не настроен',
                      )
                    }
                  } catch {
                    setCpDirectoryError('Не удалось загрузить контрагентов из xlsx')
                  } finally {
                    setCpDirectoryLoading(false)
                  }
                }}
              >
                {cpDirectoryLoading ? 'Загрузка…' : 'Загрузить контрагентов из Excel'}
              </button>
              <input
                placeholder="Поиск по названию"
                value={cpPhoneFilter}
                onChange={(e) => setCpPhoneFilter(e.target.value)}
                style={{ minWidth: 200 }}
              />
              <button
                className="btn-primary"
                disabled={cpDirectory.length === 0}
                onClick={async () => {
                  if (!selectedTrcId) return
                  const toSave = cpDirectory
                    .filter((r) => (r.phone || '').trim())
                    .map((r) => ({
                      one_c_counterparty_id: r.one_c_counterparty_id,
                      counterparty_name: r.counterparty_name,
                      contact_name: r.contact_name,
                      phone: (r.phone || '').trim(),
                    }))
                  try {
                    await adminApi.saveCounterpartyPhones(
                      selectedTrcId,
                      toSave,
                      editingTenantId || tenants[0]?.id,
                    )
                    showToast(`Сохранено телефонов: ${toSave.length}`, 'success')
                  } catch (err: unknown) {
                    const axiosErr = err as { response?: { data?: { detail?: unknown } } }
                    const detail = axiosErr.response?.data?.detail
                    // detail — строка для наших HTTPException, но для 422 от Pydantic
                    // это объект/массив ({type, loc, msg, ...}) — такое нельзя рендерить
                    // как есть, иначе падает всё дерево тостов.
                    const message =
                      typeof detail === 'string' ? detail : 'Не удалось сохранить телефоны'
                    showToast(message, 'error')
                  } finally {
                    // Даже при ошибке (например, частичный сбой синка с 1С) часть
                    // телефонов могла уже сохраниться в БД — обновляем список,
                    // чтобы админ видел реальное состояние, а не молчание.
                    setPhoneRefreshKey((k) => k + 1)
                  }
                }}
              >
                Сохранить телефоны
              </button>
            </div>
            {cpDirectoryError && <div className="error">{cpDirectoryError}</div>}
            {cpDirectory.length > 0 && (
              <div style={{ maxHeight: 360, overflow: 'auto' }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Контрагент (1С)</th>
                      <th>БИН</th>
                      <th>Контакт</th>
                      <th>Телефон получателя</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cpDirectory
                      .filter((r) =>
                        r.counterparty_name
                          .toLowerCase()
                          .includes(cpPhoneFilter.toLowerCase()),
                      )
                      .map((row) => (
                        <tr key={row.one_c_counterparty_id}>
                          <td style={{ maxWidth: 280 }}>{row.counterparty_name}</td>
                          <td>{row.bin_value || '—'}</td>
                          <td>{row.contact_name || '—'}</td>
                          <td>
                            <input
                              value={row.phone || ''}
                              placeholder="+7700..."
                              onChange={(e) => {
                                const phone = e.target.value
                                setCpDirectory((prev) =>
                                  prev.map((p) =>
                                    p.one_c_counterparty_id === row.one_c_counterparty_id
                                      ? { ...p, phone }
                                      : p,
                                  ),
                                )
                              }}
                            />
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <SavedPhonesCard trcId={selectedTrcId} refreshKey={phoneRefreshKey} />
          <BackfillPanel trcId={selectedTrcId} tenants={tenants} />
        </>
      )}

      {activeTab === 'tenants' && selectedTrcId && (
        <>
          <div className="card">
            <h3>
              Список арендаторов ({tenants.length})
              {selectedTrc ? ` — «${selectedTrc.name}»` : ''}
            </h3>
            {tenantsLoadError && <div className="error">{tenantsLoadError}</div>}
            {tenants.length === 0 && !tenantsLoadError && (
              <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 12px' }}>
                Переименование ТРЦ не удаляет арендаторов — они остаются у того же центра.
                Если список пуст, обновите страницу или проверьте, что админка подключена к нужному
                серверу API.
              </p>
            )}
            <table className="table">
              <thead>
                <tr>
                  <th>Название</th>
                  <th>ИП/ТОО</th>
                  <th>БИН/ИИН</th>
                  <th>Телефон</th>
                  <th>Логин сайта</th>
                  <th>1С логин</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {tenants.map((tenant) => (
                  <tr key={tenant.id}>
                    <td>{tenant.name}</td>
                    <td>
                      {tenant.org_type}: {tenant.legal_name}
                    </td>
                    <td>
                      {tenant.bin_value || '-'} / {tenant.iin_value || '-'}
                    </td>
                    <td>{tenant.phone || '-'}</td>
                    <td>{tenant.portal_username || '—'}</td>
                    <td>{tenant.one_c_login}</td>
                    <td>
                      <button
                        className="btn-secondary"
                        onClick={() => {
                          setTenantSaveNotice('')
                          startEditTenant(tenant)
                        }}
                      >
                        Изменить
                      </button>{' '}
                      <button
                        className="btn-danger"
                        onClick={async () => {
                          if (!confirm(`Удалить арендатора «${tenant.name}»?`)) return
                          try {
                            await adminApi.deleteTenant(selectedTrcId, tenant.id)
                            await loadTenants(selectedTrcId)
                            showToast('Арендатор удалён', 'success')
                          } catch (err: unknown) {
                            const axiosErr = err as { response?: { data?: { detail?: string } } }
                            showToast(
                              axiosErr.response?.data?.detail || 'Не удалось удалить арендатора',
                              'error',
                            )
                          }
                        }}
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {activeTab === 'whatsapplog' && selectedTrcId && (
        <WhatsAppLogPanel trcId={selectedTrcId} tenants={tenants} />
      )}

      {isSuper && activeTab === 'autonotify' && <AutoNotifyPanel tenants={tenants} />}
      {isSuper && activeTab === 'adminusers' && <AdminUserCreatePanel />}
    </div>
  )
}
