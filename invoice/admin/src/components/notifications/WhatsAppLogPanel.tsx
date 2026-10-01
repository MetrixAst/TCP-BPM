import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { adminApi, type Tenant, type WhatsAppLogEntry } from '../../api'

const PAGE_SIZE = 50

const NOTIFICATION_TYPE_LABEL: Record<string, string> = {
  week_before: 'За неделю',
  three_days: 'За 3 дня',
  same_day: 'В день оплаты',
  overdue: 'Просрочка',
}

const STATUS_LABEL: Record<string, string> = {
  sent: 'Отправлено',
  delivered: 'Доставлено',
  read: 'Прочитано',
}

function formatDateTime(value: string) {
  try {
    return new Date(value).toLocaleString('ru-RU')
  } catch {
    return value
  }
}

export function WhatsAppLogPanel({ trcId, tenants }: { trcId: number; tenants: Tenant[] }) {
  const [tenantId, setTenantId] = useState<number | ''>('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [offset, setOffset] = useState(0)
  const [items, setItems] = useState<WhatsAppLogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await adminApi.getWhatsAppLog(trcId, {
        tenantId: tenantId ? Number(tenantId) : undefined,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch {
      setError('Не удалось загрузить журнал отправок')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trcId, tenantId, dateFrom, dateTo, offset])

  const resetAndReload = () => {
    setOffset(0)
  }

  const page = Math.floor(offset / PAGE_SIZE) + 1
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="card">
      <h3>Журнал WhatsApp ({total})</h3>
      <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
        Ручные и массовые отправки (/send, /send-debtors) + автоматические напоминания по расписанию.
        Отправка файла (/send-file) сюда не попадает — для неё лог не ведётся, только обновляется дата
        последней отправки у контрагента.
      </p>
      <div className="row" style={{ marginBottom: 12 }}>
        <label>
          Арендатор
          <select
            value={tenantId}
            onChange={(e) => {
              setTenantId(e.target.value ? Number(e.target.value) : '')
              resetAndReload()
            }}
          >
            <option value="">Все арендаторы ТРЦ</option>
            {tenants.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          С
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => {
              setDateFrom(e.target.value)
              resetAndReload()
            }}
          />
        </label>
        <label>
          По
          <input
            type="date"
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.target.value)
              resetAndReload()
            }}
          />
        </label>
      </div>
      {error && <div className="error">{error}</div>}
      {loading && <p style={{ fontSize: 13, color: '#6b7280' }}>Загрузка…</p>}
      {!loading && items.length === 0 && !error && (
        <p style={{ fontSize: 13, color: '#6b7280', margin: '8px 0 0' }}>Нет записей за выбранный период</p>
      )}
      {items.length > 0 && (
        <div style={{ maxHeight: 480, overflow: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Дата</th>
                <th>Тип</th>
                <th>Способ</th>
                <th>Арендатор</th>
                <th>Контрагент</th>
                <th>Счёт</th>
                <th>Телефон</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => (
                <tr key={idx}>
                  <td>{formatDateTime(item.sent_at)}</td>
                  <td>
                    {item.notification_type ? NOTIFICATION_TYPE_LABEL[item.notification_type] || item.notification_type : '—'}
                    {item.service_type ? ` (${item.service_type})` : ''}
                  </td>
                  <td>
                    <span className={item.source === 'auto' ? 'mx-badge-partial' : 'mx-badge-neutral'}>
                      {item.source === 'auto' ? 'Авто' : 'Ручная'}
                    </span>
                  </td>
                  <td>{item.ip_name || '—'}</td>
                  <td style={{ maxWidth: 220 }}>{item.counterparty_name || '—'}</td>
                  <td>{item.invoice_id || '—'}</td>
                  <td>{item.phone_number || '—'}</td>
                  <td>{item.status ? STATUS_LABEL[item.status] || item.status : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {total > PAGE_SIZE && (
        <div className="row" style={{ marginTop: 12, alignItems: 'center', gap: 8 }}>
          <button
            className="mx-pagination-item"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            <ChevronLeft size={18} />
          </button>
          <span style={{ fontSize: 13, color: '#6b7280' }}>
            {page} / {totalPages}
          </span>
          <button
            className="mx-pagination-item"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            <ChevronRight size={18} />
          </button>
        </div>
      )}
    </div>
  )
}
