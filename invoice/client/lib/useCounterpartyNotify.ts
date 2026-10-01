'use client'

import { useCallback, useState } from 'react'
import type { NotifyModalState } from '@/components/CounterpartyNotifyModal'
import { Counterparty, Payment, paymentApi } from '@/lib/api'
import {
  extractPhoneOptions,
  type InvoiceServiceType,
  SERVICE_TYPE_LABELS,
} from '@/lib/counterpartyPhoneUtils'
import {
  formatApiError,
  isNotificationGatewayTimeout,
  notificationSendDeferredMessage,
  notificationSendResultMessage,
  notificationTypeForCounterparty,
} from '@/lib/notificationHelpers'
import { useToast } from '@/lib/toastContext'

export function useCounterpartyNotify() {
  const toast = useToast()
  const [notifyModal, setNotifyModal] = useState<NotifyModalState | null>(null)

  const openNotifyModal = useCallback(
    (
      counterparty: Counterparty,
      phoneOptions: string[],
      initialPhone?: string,
      extra?: { notificationType?: string; paymentId?: number },
    ) => {
      const options =
        phoneOptions.length > 0
          ? phoneOptions
          : extractPhoneOptions(counterparty)
      const selectedPhone =
        initialPhone && (options.length === 0 || options.includes(initialPhone))
          ? initialPhone
          : options[0] || ''
      setNotifyModal({
        counterparty,
        phoneOptions: options,
        selectedPhone,
        addPhoneValue: '',
        // Не предвыбираем "Аренда" по умолчанию — пользователь должен
        // выбрать тип явно, иначе отправляем без типа вовсе (см.
        // notificationHelpers.ts typeSuffix).
        serviceType: undefined,
        sending: false,
        notificationType: extra?.notificationType,
        paymentId: extra?.paymentId,
      })
    },
    [],
  )

  const openNotifyModalFromPayment = useCallback(
    (payment: Payment, notificationType: string, phoneNumber?: string) => {
      if (!payment.counterparty_id) {
        toast(
          'У платежа нет привязки к контрагенту 1С. Обновите реестр или отправьте из карточки контрагента.',
          'error',
        )
        return
      }
      const counterparty: Counterparty = {
        id: payment.counterparty_id,
        fullName: payment.tenant_name,
        latestInvoice: payment.invoice_id
          ? { invoiceId: payment.invoice_id }
          : undefined,
        bankAccounts: [],
        contracts: [],
        phone: phoneNumber,
        phoneNumber: phoneNumber,
      }
      const phones = phoneNumber ? [phoneNumber] : []
      openNotifyModal(counterparty, phones, phoneNumber, {
        notificationType,
        paymentId: payment.id,
      })
    },
    [openNotifyModal, toast],
  )

  const sendNotificationDirect = useCallback(
    async (params: {
      counterparty: Counterparty
      phoneNumber: string
      serviceType?: InvoiceServiceType
      notificationType?: string
      paymentId?: number
    }) => {
      const phoneNumber = params.phoneNumber.trim()
      if (!phoneNumber) {
        toast('Введите номер телефона', 'error')
        return false
      }
      const counterparty = params.counterparty
      try {
        const notificationType =
          params.notificationType || notificationTypeForCounterparty(counterparty)
        const notification = await paymentApi.sendNotification(
          notificationType,
          phoneNumber,
          counterparty.id || '',
          counterparty.latestInvoice?.invoiceId || undefined,
          params.paymentId,
          { immediate: false, serviceType: params.serviceType },
        )
        const reportTypeLabel = params.serviceType ? SERVICE_TYPE_LABELS[params.serviceType] : undefined
        toast(notificationSendResultMessage(notification, reportTypeLabel), 'success')
        return true
      } catch (error: unknown) {
        console.error('Error sending notification:', error)
        if (isNotificationGatewayTimeout(error)) {
          const reportTypeLabel = params.serviceType ? SERVICE_TYPE_LABELS[params.serviceType] : undefined
          toast(notificationSendDeferredMessage(reportTypeLabel))
          return true
        }
        toast(`Ошибка отправки уведомления: ${formatApiError(error)}`, 'error')
        return false
      }
    },
    [toast],
  )

  const handleSendFromModal = useCallback(async () => {
    if (!notifyModal) return
    setNotifyModal({ ...notifyModal, sending: true })
    const ok = await sendNotificationDirect({
      counterparty: notifyModal.counterparty,
      phoneNumber: notifyModal.selectedPhone,
      serviceType: notifyModal.serviceType,
      notificationType: notifyModal.notificationType,
      paymentId: notifyModal.paymentId,
    })
    setNotifyModal(null)
    return ok
  }, [notifyModal, sendNotificationDirect])

  return {
    notifyModal,
    setNotifyModal,
    openNotifyModal,
    openNotifyModalFromPayment,
    handleSendFromModal,
    sendNotificationDirect,
  }
}
