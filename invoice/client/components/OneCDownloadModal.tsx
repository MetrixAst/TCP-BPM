'use client'

import { useState, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { paymentApi } from '@/lib/api'
import { getApiBaseUrl } from '@/lib/apiBaseUrl'
import { getEffectiveTenantId } from '@/lib/tenantContext'
import { getPortalToken } from '@/lib/tenantAuth'
import { useToast } from '@/lib/toastContext'
import { formatBlobApiError } from '@/lib/notificationHelpers'
import { X, Download, Send } from 'lucide-react'

interface Invoice {
  id: string
  number: string
  date: string
  counterparty_id?: string
  counterparty_name?: string
  amount: number
  currency: string
  status: string
}

interface OneCDownloadModalProps {
  isOpen: boolean
  onClose: () => void
  period?: string
}

export default function OneCDownloadModal({ isOpen, onClose, period }: OneCDownloadModalProps) {
  const t = useTranslations('oneCDownload')
  const toast = useToast()
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [phoneNumber, setPhoneNumber] = useState('')
  const [showSendDialog, setShowSendDialog] = useState(false)
  const [downloadedFile, setDownloadedFile] = useState<File | null>(null)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (isOpen) {
      loadInvoices()
    }
  }, [isOpen, period])

  const loadInvoices = async () => {
    setLoading(true)
    try {
      const data = await paymentApi.get1CInvoices(period)
      setInvoices(data.invoices || [])
    } catch (error) {
      console.error('Error loading invoices:', error)
      toast(t('loadInvoicesFailed'), 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = async (invoice: Invoice) => {
    if (!invoice.counterparty_id) {
      toast(t('noCounterparty'), 'error')
      return
    }
    setDownloadingId(invoice.id)
    toast(t('downloadingHint'), 'info')
    try {
      const blob = await paymentApi.download1CInvoice(invoice.id, invoice.counterparty_id)

      // Create file from blob
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `invoice_${invoice.number}.pdf`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      // Convert blob to File for sending
      const file = new File([blob], `invoice_${invoice.number}.pdf`, { type: 'application/pdf' })
      setDownloadedFile(file)
      setSelectedInvoice(invoice)
      setShowSendDialog(true)
    } catch (error) {
      console.error('Error downloading invoice:', error)
      toast(
        t('downloadFailed', { error: await formatBlobApiError(error) }),
        'error',
      )
    } finally {
      setDownloadingId(null)
    }
  }

  const handleSend = async () => {
    if (!phoneNumber || !selectedInvoice || !downloadedFile) return

    setSending(true)
    try {
      // Create FormData for file upload
      const formData = new FormData()
      formData.append('file', downloadedFile)
      formData.append('phone_number', phoneNumber)
      formData.append('invoice_id', selectedInvoice.id)
      if (selectedInvoice.counterparty_id) {
        formData.append('counterparty_id', selectedInvoice.counterparty_id)
      }
      const tenantId = getEffectiveTenantId()
      if (tenantId) {
        formData.append('tenant_id', String(tenantId))
      }

      // Send via WhatsApp
      const token = getPortalToken()
      const response = await fetch(`${getApiBaseUrl()}/api/notifications/send-file`, {
        method: 'POST',
        body: formData,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })

      const result = await response.json()

      if (response.ok && result.success) {
        toast(t('sentSuccess'), 'success')
        setShowSendDialog(false)
        setPhoneNumber('')
        setDownloadedFile(null)
        setSelectedInvoice(null)
        onClose()
      } else {
        throw new Error(result.message || result.detail || 'Failed to send file')
      }
    } catch (error: any) {
      console.error('Error sending file:', error)
      toast(t('sendFailed', { error: error.message || error }), 'error')
    } finally {
      setSending(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center">
          <h2 className="text-xl font-semibold">{t('title')}</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700"
          >
            <X size={24} />
          </button>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="text-center py-8">{t('loading')}</div>
          ) : invoices.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              {t('notFound')}
            </div>
          ) : (
            <div className="space-y-2">
              {invoices.map((invoice) => (
                <div
                  key={invoice.id}
                  className="border rounded-lg p-4 flex justify-between items-center hover:bg-gray-50"
                >
                  <div>
                    <div className="font-medium">{t('invoiceNumber', { number: invoice.number })}</div>
                    <div className="text-sm text-gray-600">
                      {invoice.counterparty_name} • {new Date(invoice.date).toLocaleDateString('ru-RU')} • {invoice.amount} {invoice.currency}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDownload(invoice)}
                    disabled={downloadingId !== null}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
                  >
                    <Download size={16} />
                    {downloadingId === invoice.id ? t('downloading') : t('download')}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {showSendDialog && (
          <div className="border-t p-6 bg-gray-50">
            <h3 className="font-medium mb-4">{t('sendTitle')}</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('phoneLabel')}
                </label>
                <input
                  type="tel"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  placeholder={t('phonePlaceholder')}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2"
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleSend}
                  disabled={!phoneNumber || sending}
                  className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  <Send size={16} />
                  {sending ? t('sending') : t('send')}
                </button>
                <button
                  onClick={() => {
                    setShowSendDialog(false)
                    setPhoneNumber('')
                    setDownloadedFile(null)
                  }}
                  className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400"
                >
                  {t('cancel')}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
