import { oneCApi } from './api'

export async function waitForCounterpartySync(params: {
  limit?: number
  period?: string
  includeInvoiceStatus?: boolean
  timeoutMs?: number
}): Promise<{ done: boolean; sync_error?: string; warning?: string }> {
  const limit = params.limit ?? 10000
  const deadline = Date.now() + (params.timeoutMs ?? 180000)

  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 2500))
    const response = await oneCApi.getCounterparties(limit, {
      include_invoice_status: params.includeInvoiceStatus,
      period: params.period,
    })
    if (response.sync_status === 'failed') {
      return {
        done: false,
        sync_error: response.sync_error || 'Синхронизация не удалась',
      }
    }
    if (response.sync_status === 'done' || response.sync_status !== 'running') {
      return {
        done: true,
        sync_error: response.sync_error,
        warning: response.warning,
      }
    }
  }

  return {
    done: false,
    sync_error: 'Синхронизация ещё идёт. Обновите страницу через минуту.',
  }
}
