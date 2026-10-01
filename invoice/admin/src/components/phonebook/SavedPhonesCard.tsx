import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { adminApi, type CounterpartyPhoneResponse } from '../../api'
import { useToast } from '../../lib/toast'

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('ru-RU')
  } catch {
    return value
  }
}

export function SavedPhonesCard({ trcId, refreshKey }: { trcId: number; refreshKey: number }) {
  const showToast = useToast()
  const [phones, setPhones] = useState<CounterpartyPhoneResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const reload = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await adminApi.listCounterpartyPhones(trcId)
      setPhones(data)
    } catch {
      setError('Не удалось загрузить сохранённые телефоны')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trcId, refreshKey])

  const hasServiceSplit = phones.some((p) => p.phone_rent || p.phone_utilities || p.phone_operations)

  const handleDelete = async (row: CounterpartyPhoneResponse) => {
    if (
      !window.confirm(
        `Удалить телефон получателя «${row.counterparty_name || row.one_c_counterparty_id}»?`,
      )
    ) {
      return
    }
    setDeletingId(row.id)
    try {
      await adminApi.deleteCounterpartyPhone(trcId, row.id)
      showToast('Телефон удалён', 'success')
      await reload()
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      if (axiosErr.response?.status === 404) {
        showToast('Запись уже удалена', 'error')
        await reload()
      } else {
        showToast(axiosErr.response?.data?.detail || 'Не удалось удалить телефон', 'error')
      }
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="card">
      <h3>Сохранённые телефоны ({phones.length})</h3>
      {loading && <p style={{ fontSize: 13, color: '#6b7280' }}>Загрузка…</p>}
      {error && <div className="error">{error}</div>}
      {!loading && phones.length === 0 && !error && (
        <p style={{ fontSize: 13, color: '#6b7280', margin: '8px 0 0' }}>
          Нет сохранённых телефонов
        </p>
      )}
      {phones.length > 0 && (
        <div style={{ maxHeight: 360, overflow: 'auto', marginTop: 8 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Контрагент</th>
                <th>Контакт</th>
                <th>Телефон</th>
                {hasServiceSplit && <th>Аренда</th>}
                {hasServiceSplit && <th>КУ</th>}
                {hasServiceSplit && <th>Услуги</th>}
                <th>Посл. отправка WhatsApp</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {phones.map((row) => (
                <tr key={row.id}>
                  <td style={{ maxWidth: 280 }}>{row.counterparty_name || row.one_c_counterparty_id}</td>
                  <td>{row.contact_name || '—'}</td>
                  <td>{row.phone}</td>
                  {hasServiceSplit && <td>{row.phone_rent || '—'}</td>}
                  {hasServiceSplit && <td>{row.phone_utilities || '—'}</td>}
                  {hasServiceSplit && <td>{row.phone_operations || '—'}</td>}
                  <td>{formatDateTime(row.last_whatsapp_sent_at)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn-danger"
                      disabled={deletingId === row.id}
                      onClick={() => handleDelete(row)}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                    >
                      <Trash2 size={14} />
                      {deletingId === row.id ? 'Удаление…' : 'Удалить'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
