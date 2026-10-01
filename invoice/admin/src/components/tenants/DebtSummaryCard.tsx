import { useEffect, useState } from 'react'
import { adminApi, TrcDebtSummary } from '../../api'
import { useToast } from '../../lib/toast'

function formatTenge(value: number): string {
  return `${Math.round(value).toLocaleString('ru-RU')} ₸`
}

const AGING_LABELS: { key: keyof TrcDebtSummary['aging']; label: string }[] = [
  { key: 'current', label: 'Без просрочки' },
  { key: 'days30', label: 'До 30 дн' },
  { key: 'days60', label: '31–60 дн' },
  { key: 'days90', label: '61–90 дн' },
  { key: 'over120', label: '120+ дн' },
  { key: 'unknown', label: 'Срок неизвестен' },
]

export function DebtSummaryCard({ trcId }: { trcId: number }) {
  const [summary, setSummary] = useState<TrcDebtSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const showToast = useToast()

  useEffect(() => {
    let cancelled = false
    setSummary(null)
    setLoading(true)
    adminApi
      .getTrcDebtSummary(trcId)
      .then((data) => {
        if (!cancelled) setSummary(data)
      })
      .catch((err) => {
        if (!cancelled)
          showToast(err?.response?.data?.detail || 'Не удалось загрузить сводку долга', 'error')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trcId])

  if (loading) {
    return (
      <div className="mx-card mb-6 p-6 text-sm text-slate-500">Загрузка сводки долга…</div>
    )
  }
  if (!summary) return null

  const hasAnyData = summary.tenants_with_data > 0

  return (
    <div className="mx-card mb-6">
      <div className="mx-card-header flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">Долг по арендаторам — сводка</h3>
        {summary.tenants_without_data > 0 && (
          <span className="mx-badge-neutral">
            {summary.tenants_without_data === 1
              ? '1 арендатор без данных из 1С'
              : `${summary.tenants_without_data} арендаторов без данных из 1С`}
          </span>
        )}
      </div>
      <div className="p-6">
        {!hasAnyData ? (
          <p className="text-sm text-slate-500">
            Нет засинканного снимка баланса ни по одному арендатору этого ТРЦ — синк либо ещё не
            запускался, либо недоступен для текущего способа подключения к 1С.
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">Общий долг</p>
                <p className="text-xl font-semibold text-slate-800 tabular-nums">{formatTenge(summary.total_debt)}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">Общий аванс</p>
                <p className="text-xl font-semibold text-slate-800 tabular-nums">{formatTenge(summary.total_advance)}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">Арендаторов с данными</p>
                <p className="text-xl font-semibold text-slate-800 tabular-nums">{summary.tenants_with_data}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">Из них без срока (aging)</p>
                <p className="text-xl font-semibold text-slate-800 tabular-nums">{formatTenge(summary.aging.unknown)}</p>
              </div>
            </div>

            <p className="text-xs uppercase tracking-wide text-slate-400 mb-2">Долг по срокам просрочки</p>
            <div className="flex flex-wrap gap-2 mb-6">
              {AGING_LABELS.map(({ key, label }) => (
                <span key={key} className="mx-badge-neutral tabular-nums">
                  {label}: {formatTenge(summary.aging[key])}
                </span>
              ))}
            </div>
            <p className="text-xs text-slate-400 mb-4">
              Часть долга закономерно попадает в «срок неизвестен» — у некоторых организаций 1С не
              ведёт учёт по документам расчётов, это ограничение исходных данных, не ошибка синка.
            </p>

            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="mx-table-head">
                  <tr>
                    <th className="mx-table-th">Арендатор</th>
                    <th className="mx-table-th">Долг</th>
                    <th className="mx-table-th">Аванс</th>
                    <th className="mx-table-th">Синк</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_tenant.map((t) => (
                    <tr key={t.tenant_id} className="border-b border-slate-50 last:border-0">
                      <td className="mx-table-td">{t.tenant_name}</td>
                      {t.has_balance_data ? (
                        <>
                          <td className="mx-table-td tabular-nums">{formatTenge(t.debt)}</td>
                          <td className="mx-table-td tabular-nums">{formatTenge(t.advance)}</td>
                          <td className="mx-table-td text-slate-400">
                            {t.synced_at ? new Date(t.synced_at).toLocaleString('ru-RU') : '—'}
                          </td>
                        </>
                      ) : (
                        <td className="mx-table-td text-slate-400" colSpan={3}>
                          Нет данных — синк баланса недоступен или ещё не запускался
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
