'use client'

import { useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { tenantAuthApi, xlsxImportApi, XlsxImportSummary } from '@/lib/api'
import { formatApiError } from '@/lib/notificationHelpers'
import { useToast } from '@/lib/toastContext'
import TabRefreshButton from './TabRefreshButton'

interface XlsxUploadPanelProps {
  /** Реестр (tenant_payments) уже обновлён в БД к моменту ответа upload —
   * бэкенд делает parse -> normalize -> upsert синхронно в том же запросе
   * (см. app/api/xlsx_import.py). Таблица на экране просто не знает, что
   * нужно перечитать данные — этот колбэк (обычно loadPaymentsTab из
   * PaymentRegistry) закрывает именно это, не сам импорт. */
  onImported?: () => void | Promise<void>
}

/** Самостоятельный блок — сам спрашивает /me, есть ли у арендатора право
 * грузить xlsx (xlsx_upload_available требует и настроенный parser_key, и
 * xlsx_priority != disabled одновременно, см. invoice-backend
 * tenant_auth.py), и если нет — ничего не рендерит. Не завязан на
 * TenantPortalSession в localStorage специально: право включает/выключает
 * админ, и должно быть видно сразу после релогина/обновления страницы, а
 * не только после явного refreshPortalSession() где-то ещё в дереве. */
export default function XlsxUploadPanel({ onImported }: XlsxUploadPanelProps) {
  const t = useTranslations('xlsxUpload')
  const toast = useToast()
  const [available, setAvailable] = useState(false)
  const [checking, setChecking] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [result, setResult] = useState<XlsxImportSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    tenantAuthApi
      .me()
      .then((data) => {
        if (!cancelled) setAvailable(Boolean(data.xlsx_upload_available))
      })
      .catch(() => {
        if (!cancelled) setAvailable(false)
      })
      .finally(() => {
        if (!cancelled) setChecking(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (checking || !available) return null

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError(null)
    setResult(null)
    try {
      const summary = await xlsxImportApi.upload(file)
      setResult(summary)
      // Строки уже в БД к этому моменту (см. onImported doc) — обновляем
      // таблицу сразу, без ожидания клика на кнопку ниже. Кнопка остаётся
      // как явное подтверждение + возможность перечитать ещё раз вручную.
      if (onImported) await onImported()
    } catch (err) {
      setError(formatApiError(err))
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleRefreshClick = async () => {
    if (!onImported) return
    setRefreshing(true)
    try {
      await onImported()
      toast(t('refreshedToast'), 'success')
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="block" style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12 }}>
      <p className="block_title">{t('title')}</p>
      <p style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{t('hint')}</p>
      <div className="row gap-4" style={{ marginTop: 8, alignItems: 'center' }}>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx"
          disabled={uploading}
          onChange={handleFileChange}
        />
        {uploading && <span>{t('uploading')}</span>}
      </div>

      {error && (
        <div style={{ marginTop: 10, color: '#b91c1c', fontSize: 13 }}>{t('uploadFailed', { error })}</div>
      )}

      {result && (
        <div style={{ marginTop: 10, fontSize: 13 }}>
          {/* Явный статус первым делом — до этого весь блок был одним
           * нейтральным текстом, и было не видно с первого взгляда,
           * сработала загрузка или нет (см. скриншот пользователя). */}
          <p style={{ fontWeight: 700, color: result.rows_total > 0 ? '#15803d' : '#b45309' }}>
            {result.rows_total > 0 ? t('successHeadline') : t('noRowsHeadline')}
          </p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>
            {t('resultPeriods', { periods: result.periods.join(', ') || '—' })}
          </p>
          <p>
            {t('resultRows', {
              total: result.rows_total,
              created: result.rows_created,
              updated: result.rows_updated,
            })}
          </p>
          {result.rows_deleted > 0 && (
            <p style={{ color: '#6b7280' }}>{t('resultDeleted', { deleted: result.rows_deleted })}</p>
          )}
          <p>
            {t('resultMatched', {
              matched: result.rows_matched,
              unmatched: result.rows_unmatched,
            })}
          </p>
          {onImported && (
            <div style={{ marginTop: 8 }}>
              <TabRefreshButton onClick={handleRefreshClick} loading={refreshing} label={t('refreshButton')} />
            </div>
          )}
          {result.unmatched_names.length > 0 && (
            <details style={{ marginTop: 6 }}>
              <summary>{t('unmatchedNamesSummary', { count: result.unmatched_names.length })}</summary>
              <ul style={{ margin: '4px 0 0 16px' }}>
                {result.unmatched_names.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            </details>
          )}
          {Object.entries(result.totals_check).some(([, check]) => !check.ok) && (
            <p style={{ color: '#b45309', marginTop: 6 }}>{t('totalsCheckFailed')}</p>
          )}
          {result.warnings.length > 0 && (
            <ul style={{ margin: '6px 0 0 16px', color: '#b45309' }}>
              {result.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
