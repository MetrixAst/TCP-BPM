'use client'

import { useState, useRef, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import Image from 'next/image'
import { Payment, Counterparty, paymentApi } from '@/lib/api'
import { catalogApi } from '@/lib/catalogApi'
import { extractPhoneOptions, type InvoiceServiceType } from '@/lib/counterpartyPhoneUtils'
import { enabledPaymentTypes } from '@/lib/paymentTypesContext'
import { getEffectiveTenantId } from '@/lib/tenantContext'
import { useCounterpartyNotify } from '@/lib/useCounterpartyNotify'
import { formatApiError, notificationTypeForStatus } from '@/lib/notificationHelpers'
import { useToast } from '@/lib/toastContext'
import whatsappIcon from '@/assets/logo/WhatsApp_icon.png'

function formatDisplayPhone(phone: string): string {
  const digits = phone.replace(/\D/g, '')
  if (digits.length === 11 && digits.startsWith('7')) {
    return `+7 ${digits.slice(1, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`
  }
  if (digits.length === 10) {
    return `+7 ${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`
  }
  return phone
}

interface NotificationPopoverProps {
  payment?: Payment
  counterparty?: Counterparty
  phoneNumber?: string
  paymentStatus?: string
}

export default function NotificationPopover({
  payment,
  counterparty: counterpartyProp,
  phoneNumber,
  paymentStatus,
}: NotificationPopoverProps) {
  const t = useTranslations('notifications')
  const tCommon = useTranslations('common')
  const toast = useToast()
  const [isOpen, setIsOpen] = useState(false)
  const [sending, setSending] = useState(false)
  const [sendingEmail, setSendingEmail] = useState(false)
  // Не предвыбираем "Аренда" по умолчанию — см. useCounterpartyNotify.ts.
  const [serviceType, setServiceType] = useState<InvoiceServiceType | undefined>(undefined)
  const [phoneOptions, setPhoneOptions] = useState<string[]>([])
  const [phoneRent, setPhoneRent] = useState('')
  const [phoneUtilities, setPhoneUtilities] = useState('')
  const [phoneOperations, setPhoneOperations] = useState('')
  const [selectedPhone, setSelectedPhone] = useState(phoneNumber || '')
  const popoverRef = useRef<HTMLDivElement>(null)
  const paymentId = payment?.id
  const popoverId = `notify-${paymentId ?? counterpartyProp?.id ?? phoneNumber ?? 'cp'}`
  const { sendNotificationDirect } = useCounterpartyNotify()

  const counterparty: Counterparty | null =
    counterpartyProp ||
    (payment?.counterparty_id
      ? {
          id: payment.counterparty_id,
          fullName: payment.tenant_name,
          latestInvoice: payment.invoice_id ? { invoiceId: payment.invoice_id } : undefined,
          bankAccounts: [],
          contracts: [],
          phone: phoneNumber || '',
          phoneNumber: phoneNumber || '',
        }
      : null)

  const status = paymentStatus ?? payment?.status ?? counterpartyProp?.latestInvoice?.paymentStatus

  const resolvePhoneForService = (
    type: InvoiceServiceType | undefined,
    phones: string[],
    rent: string,
    utilities: string,
    operations: string,
    fallback: string,
  ) => {
    if (type === 'rent' && rent && phones.includes(rent)) return rent
    if (type === 'utilities' && utilities && phones.includes(utilities)) return utilities
    if (type === 'operations' && operations && phones.includes(operations)) return operations
    return fallback || phones[0] || ''
  }

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      const loadPhones = async () => {
        if (!counterparty?.id || !getEffectiveTenantId()) {
          const local = extractPhoneOptions(counterparty || ({} as Counterparty), [])
          setPhoneOptions(local)
          setSelectedPhone(resolvePhoneForService(serviceType, local, '', '', '', phoneNumber || ''))
          return
        }
        try {
          const data = await catalogApi.getCounterpartyPhones(counterparty.id)
          const rent = data.phone_rent || ''
          const utilities = data.phone_utilities || ''
          const operations = data.phone_operations || ''
          const phones = extractPhoneOptions(counterparty, data.phones || [])
          setPhoneOptions(phones)
          setPhoneRent(rent)
          setPhoneUtilities(utilities)
          setPhoneOperations(operations)
          setSelectedPhone(
            resolvePhoneForService(serviceType, phones, rent, utilities, operations, phoneNumber || ''),
          )
        } catch (err) {
          console.warn('Failed to load counterparty phones', err)
          const local = extractPhoneOptions(counterparty, [])
          setPhoneOptions(local)
          setSelectedPhone(resolvePhoneForService(serviceType, local, '', '', '', phoneNumber || ''))
        }
      }
      void loadPhones()
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen, counterparty?.id, phoneNumber])

  const pickPhoneForService = (type: InvoiceServiceType) => {
    setSelectedPhone(
      resolvePhoneForService(type, phoneOptions, phoneRent, phoneUtilities, phoneOperations, phoneNumber || ''),
    )
  }

  const serviceTypes = enabledPaymentTypes()

  const triggerLabel = status === 'overdue' ? t('overdue') : t('weekBefore')

  const handleSend = async () => {
    const phone = selectedPhone || phoneNumber
    if (!counterparty || !phone || sending || sendingEmail) return
    setSending(true)
    try {
      await sendNotificationDirect({
        counterparty,
        phoneNumber: phone,
        serviceType,
        notificationType: notificationTypeForStatus(status),
        paymentId,
      })
    } finally {
      setSending(false)
    }
  }

  const handleSendEmail = async () => {
    if (!counterparty?.id || sending || sendingEmail) return
    const email = (counterparty.email || '').trim()
    if (!email) {
      toast(t('noEmail'), 'error')
      return
    }
    setSendingEmail(true)
    try {
      const result = await paymentApi.sendInvoiceEmail({
        counterpartyId: counterparty.id,
        email,
        invoiceId: counterparty.latestInvoice?.invoiceId || payment?.invoice_id || undefined,
        serviceType,
        counterpartyName: counterparty.fullName,
      })
      toast(result.message || t('invoiceSentToEmail', { email }), 'success')
    } catch (error: unknown) {
      console.error('Error sending invoice email:', error)
      toast(t('emailSendError', { error: formatApiError(error) }), 'error')
    } finally {
      setSendingEmail(false)
    }
  }

  const sendPhone = selectedPhone || phoneNumber
  const sendEmail = (counterparty?.email || '').trim()

  if (!counterparty?.id && !phoneNumber && !payment?.counterparty_id) {
    return <span>—</span>
  }
  if (!counterparty) {
    return <span>—</span>
  }
  if (!sendPhone && !sendEmail) {
    return <span>—</span>
  }

  return (
    <div className="tip_drop" ref={popoverRef}>
      <p
        className={`title toggle_handler${isOpen ? ' opened' : ''}`}
        onClick={(e) => {
          e.stopPropagation()
          setIsOpen(!isOpen)
        }}
      >
        {triggerLabel}
      </p>

      <div
        id={popoverId}
        className={`toggle_content from_right${isOpen ? ' is-open' : ''}`}
        onClick={(e) => e.stopPropagation()}
        style={{ maxHeight: 'none', overflow: 'visible' }}
      >
        {serviceTypes.length > 0 && (
          <div className="column gap-s pv-8 ph-16">
            <p className="subtitle">{t('categoryLabel')}</p>
            {serviceTypes.map((type) => (
              <label key={type} className="radio circle">
                <input
                  type="radio"
                  name={`notify-service-${popoverId}`}
                  checked={serviceType === type}
                  onChange={() => {
                    setServiceType(type)
                    pickPhoneForService(type)
                  }}
                  disabled={sending}
                />
                <span className="checkmark" />
                <span>{tCommon(`serviceTypes.${type}`)}</span>
              </label>
            ))}
          </div>
        )}

        {phoneOptions.length > 1 && (
          <div className="column gap-s pv-8 ph-16">
            <p className="subtitle">{t('phoneLabel')}</p>
            {phoneOptions.map((phone) => (
              <label key={phone} className="radio circle">
                <input
                  type="radio"
                  name={`notify-phone-${popoverId}`}
                  checked={selectedPhone === phone}
                  onChange={() => setSelectedPhone(phone)}
                  disabled={sending}
                />
                <span className="checkmark" />
                <span>{formatDisplayPhone(phone)}</span>
              </label>
            ))}
          </div>
        )}

        {sendPhone && (
          <div className="row pv-8 ph-16">
            <button
              type="button"
              className="button color-green flex"
              onClick={handleSend}
              disabled={sending || sendingEmail}
            >
              <Image src={whatsappIcon} alt="" width={20} height={20} className="shrink-0" />
              {sending ? tCommon('sending') : formatDisplayPhone(sendPhone)}
            </button>
          </div>
        )}

        {sendEmail && (
          <div className="row pv-8 ph-16">
            <button
              type="button"
              className="button size-m"
              onClick={handleSendEmail}
              disabled={sending || sendingEmail}
              title={t('emailTitle', { email: sendEmail })}
            >
              {sendingEmail ? t('sendingEmail') : t('emailPrefix', { email: sendEmail })}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
