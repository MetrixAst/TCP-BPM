import { useRef, useState } from 'react'
import { adminApi, type CounterpartyPhoneBackfillItem, type CounterpartyPhoneBackfillResponse, type Tenant } from '../../api'
import { useToast } from '../../lib/toast'
import { StatusBadge } from '../ui/StatusBadge'

export function BackfillPanel({ trcId, tenants }: { trcId: number; tenants: Tenant[] }) {
  const showToast = useToast()
  const [tenantId, setTenantId] = useState<number | ''>('')
  const [dryRun, setDryRun] = useState(true)
  const [limit, setLimit] = useState(20)
  const [afterId, setAfterId] = useState(0)
  const [running, setRunning] = useState(false)
  const [batches, setBatches] = useState<CounterpartyPhoneBackfillResponse[]>([])
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const stopRef = useRef(false)

  const reset = () => {
    setBatches([])
    setAfterId(0)
    setDone(false)
    setError('')
  }

  const runOneBatch = async (): Promise<boolean> => {
    if (!tenantId) {
      setError('Выберите арендатора')
      return true
    }
    setRunning(true)
    setError('')
    try {
      const res = await adminApi.syncCounterpartyPhonesToOneC(trcId, {
        tenantId: Number(tenantId),
        dryRun,
        limit,
        afterId,
      })
      if (!res.ok) {
        setError(res.error || 'Не удалось выполнить перенос телефонов в 1С')
        return true
      }
      setBatches((prev) => [...prev, res])
      const isDone = res.items.length === 0 || res.total === 0 || res.last_processed_id == null
      if (res.last_processed_id != null) {
        setAfterId(res.last_processed_id)
      }
      return isDone
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      setError(axiosErr.response?.data?.detail || 'Не удалось выполнить перенос телефонов в 1С')
      return true
    } finally {
      setRunning(false)
    }
  }

  const handleRunOne = async () => {
    const isDone = await runOneBatch()
    if (isDone) {
      setDone(true)
      showToast('Перенос телефонов завершён', 'success')
    }
  }

  const handleRunAll = async () => {
    stopRef.current = false
    let isDone = false
    while (!stopRef.current && !isDone) {
      isDone = await runOneBatch()
    }
    if (isDone) {
      setDone(true)
      showToast('Перенос телефонов завершён', 'success')
    }
  }

  const handleStop = () => {
    stopRef.current = true
  }

  // last-write-wins de-dupe across batches (a manual retry from an earlier
  // after_id would otherwise produce duplicate rows in the results table)
  const itemsById = new Map<string, CounterpartyPhoneBackfillItem>()
  for (const batch of batches) {
    for (const item of batch.items) {
      itemsById.set(item.one_c_counterparty_id, item)
    }
  }
  const items = Array.from(itemsById.values())

  const totals = batches.reduce(
    (acc, b) => ({
      total: acc.total + b.total,
      ok: acc.ok + b.ok_count,
      fail: acc.fail + b.fail_count,
      empty: acc.empty + b.empty_skip,
    }),
    { total: 0, ok: 0, fail: 0, empty: 0 },
  )
  const lastBatch = batches[batches.length - 1]

  return (
    <div className="card">
      <h3>Перенос телефонов в 1С</h3>
      <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
        Массово записывает уже сохранённые у нас телефоны получателей в регистр контактной информации 1С.
        Работает только для арендаторов с OData-подключением (не COM). Размер пачки ограничен, чтобы не
        упереться в таймаут — при «Выполнить всё до конца» запросы идут последовательно, каждый в пределах
        лимита.
      </p>
      <div className="row" style={{ marginBottom: 12 }}>
        <label>
          Арендатор
          <select
            value={tenantId}
            onChange={(e) => {
              setTenantId(e.target.value ? Number(e.target.value) : '')
              reset()
            }}
          >
            <option value="">— выберите —</option>
            {tenants.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Размер пачки
          <input
            type="number"
            min={1}
            value={limit}
            onChange={(e) => setLimit(Math.max(1, Number(e.target.value) || 1))}
            style={{ width: 100 }}
          />
        </label>
        <label style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          Тестовый прогон (без записи в 1С)
        </label>
      </div>
      {!dryRun && (
        <p style={{ fontSize: 12, color: '#a5661a', marginBottom: 12 }}>
          Внимание: телефоны будут записаны в 1С.
        </p>
      )}
      <div className="row">
        <button className="btn-secondary" onClick={handleRunOne} disabled={running || done}>
          {running ? 'Выполняется…' : 'Выполнить одну пачку'}
        </button>
        <button className="btn-primary" onClick={handleRunAll} disabled={running || done}>
          {running ? 'Выполняется…' : 'Выполнить всё до конца'}
        </button>
        {running && (
          <button className="btn-danger" onClick={handleStop}>
            Стоп
          </button>
        )}
        <button className="btn-secondary" onClick={reset} disabled={running}>
          Сбросить
        </button>
      </div>
      {error && <div className="error">{error}</div>}
      {done && !error && (
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
          Все телефоны обработаны
        </div>
      )}
      {batches.length > 0 && (
        <>
          <p style={{ fontSize: 13, marginTop: 12 }}>
            Всего: {totals.total} · Записано: {totals.ok} · Пропущено (нет телефона): {totals.empty} ·
            Ошибок: {totals.fail}
            {lastBatch?.tenant_name ? ` · Арендатор: ${lastBatch.tenant_name}` : ''}
          </p>
          <div style={{ maxHeight: 360, overflow: 'auto', marginTop: 8 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Контрагент</th>
                  <th>Телефоны</th>
                  <th>Статус</th>
                  <th>Записано/Пропущено</th>
                  <th>Сообщение</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.one_c_counterparty_id}>
                    <td style={{ maxWidth: 240 }}>{item.counterparty_name || item.one_c_counterparty_id}</td>
                    <td>{item.phones.join(', ') || '—'}</td>
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                    <td>
                      {item.written ?? '—'} / {item.skipped ?? '—'}
                    </td>
                    <td>{item.message || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
