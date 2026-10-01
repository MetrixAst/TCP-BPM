import { useState } from 'react'
import { adminApi, type AutoNotificationRunResponse, type Tenant } from '../../api'
import { useToast } from '../../lib/toast'

export function AutoNotifyPanel({ tenants }: { tenants: Tenant[] }) {
  const showToast = useToast()
  const [tenantId, setTenantId] = useState<number | ''>('')
  const [forceWindow, setForceWindow] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<AutoNotificationRunResponse | null>(null)
  const [error, setError] = useState('')

  const handleRun = async () => {
    const scopeLabel = tenantId
      ? tenants.find((t) => t.id === Number(tenantId))?.name ?? `#${tenantId}`
      : 'ВСЕ арендаторы (всех ТРЦ)'
    const message = forceWindow
      ? `Запустить авторассылку для «${scopeLabel}» СЕЙЧАС, игнорируя окно отправки? Сообщения уйдут немедленно.`
      : `Запустить авторассылку для «${scopeLabel}»?`
    if (!window.confirm(message)) return

    setRunning(true)
    setError('')
    setResult(null)
    try {
      const res = await adminApi.runAutoNotifications({
        tenant_id: tenantId ? Number(tenantId) : undefined,
        force_window: forceWindow,
      })
      setResult(res)
      showToast(`Отправлено сообщений: ${res.sent}`, 'success')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      const detail = axiosErr.response?.data?.detail
      setError(detail || 'Не удалось запустить авторассылку')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="card">
      <h3>Ручной запуск авторассылки</h3>
      <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
        Обычно рассылка напоминаний об оплате запускается автоматически каждый час. Здесь можно запустить
        её вручную — например, чтобы проверить конкретного арендатора.
      </p>
      <div className="row" style={{ marginBottom: 4 }}>
        <label>
          Арендатор
          <select value={tenantId} onChange={(e) => setTenantId(e.target.value ? Number(e.target.value) : '')}>
            <option value="">Все арендаторы (всех ТРЦ)</option>
            {tenants.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p style={{ fontSize: 12, color: '#6b7280', margin: '0 0 12px' }}>
        «Все арендаторы» запускает рассылку по всем ТРЦ в системе, а не только по выбранному здесь ТРЦ.
      </p>
      <label style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <input type="checkbox" checked={forceWindow} onChange={(e) => setForceWindow(e.target.checked)} />
        Игнорировать окно отправки (09:00–18:00, Астана)
      </label>
      {forceWindow && (
        <p style={{ fontSize: 12, color: '#9a3f22', marginBottom: 12 }}>
          ⚠ Отладочный режим: сообщения уйдут получателям немедленно, независимо от времени суток.
        </p>
      )}
      <div className="row" style={{ marginTop: 8 }}>
        <button
          className={forceWindow ? 'btn-danger' : 'btn-primary'}
          onClick={handleRun}
          disabled={running}
        >
          {running ? 'Запуск…' : 'Запустить авторассылку'}
        </button>
      </div>
      {error && <div className="error">{error}</div>}
      {result && (
        <div
          style={{
            marginTop: 12,
            padding: '10px 14px',
            borderRadius: 8,
            background: '#ecfdf5',
            color: '#15803d',
            fontSize: 14,
          }}
        >
          Отправлено: {result.sent}
          {!result.can_send && ' — вне окна отправки, сообщения не уходили'}
        </div>
      )}
    </div>
  )
}
