'use client'

import { useTranslations } from 'next-intl'
import type { Counterparty } from '@/lib/api'

import type { InvoiceServiceType } from '@/lib/counterpartyPhoneUtils'
import { enabledPaymentTypes } from '@/lib/paymentTypesContext'

export interface NotifyModalState {
  counterparty: Counterparty
  phoneOptions: string[]
  selectedPhone: string
  addPhoneValue: string
  /** undefined — пользователь не выбрал тип явно; в этом случае не
   * отправляем service_type и не пишем тип услуги в тексте WhatsApp,
   * вместо того чтобы молча слать "Аренда" по умолчанию. */
  serviceType?: InvoiceServiceType
  sending: boolean
  /** Тип уведомления из реестра (week_before, overdue, …); иначе — по статусу счёта */
  notificationType?: string
  paymentId?: number
}

interface CounterpartyNotifyModalProps {
  modal: NotifyModalState
  onClose: () => void
  onChange: (modal: NotifyModalState) => void
  onSend: () => void
}

export default function CounterpartyNotifyModal({
  modal,
  onClose,
  onChange,
  onSend,
}: CounterpartyNotifyModalProps) {
  const t = useTranslations('notifyModal')
  const tCommon = useTranslations('common')
  const serviceTypes = enabledPaymentTypes()

  return (
    <div
      className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4"
      onClick={() => !modal.sending && onClose()}
    >
      <div
        className="w-full max-w-sm mx-card p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-gray-900">{t('title')}</h3>
        <p className="text-sm text-gray-600 mt-1">{modal.counterparty.fullName}</p>
        <div className="mt-3 space-y-3">
          <div>
            <div className="text-sm text-gray-700 mb-1">{t('phoneLabel')}</div>
            <div className="space-y-1">
              {modal.phoneOptions.map((phone) => (
                <label key={phone} className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="radio"
                    name="notify-phone"
                    checked={modal.selectedPhone === phone}
                    onChange={() => onChange({ ...modal, selectedPhone: phone })}
                    disabled={modal.sending}
                  />
                  <span>{phone}</span>
                </label>
              ))}
            </div>
            <div className="mt-2 flex gap-2">
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                value={modal.addPhoneValue}
                onChange={(e) => onChange({ ...modal, addPhoneValue: e.target.value })}
                placeholder={t('phonePlaceholder')}
                disabled={modal.sending}
              />
              <button
                type="button"
                className="px-3 py-2 text-sm rounded-lg border border-blue-300 text-blue-700"
                onClick={() => {
                  const value = modal.addPhoneValue.trim()
                  if (!value) return
                  if (modal.phoneOptions.includes(value)) {
                    onChange({ ...modal, selectedPhone: value, addPhoneValue: '' })
                    return
                  }
                  onChange({
                    ...modal,
                    phoneOptions: [...modal.phoneOptions, value],
                    selectedPhone: value,
                    addPhoneValue: '',
                  })
                }}
                disabled={modal.sending}
              >
                +
              </button>
            </div>
          </div>
          {serviceTypes.length > 0 && (
            <div>
              <div className="text-sm text-gray-700 mb-1">{t('categoryLabel')}</div>
              <div className="space-y-1">
                {serviceTypes.map((type) => (
                  <label key={type} className="flex items-center gap-2 text-sm text-gray-700">
                    <input
                      type="radio"
                      name="notify-service"
                      checked={modal.serviceType === type}
                      onChange={() => onChange({ ...modal, serviceType: type })}
                      disabled={modal.sending}
                    />
                    <span>{tCommon(`serviceTypes.${type}`)}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button
            className="px-3 py-2 text-sm rounded-lg border border-gray-300 text-gray-700"
            onClick={onClose}
            disabled={modal.sending}
          >
            {tCommon('cancel')}
          </button>
          <button
            className="mx-btn-primary px-4"
            onClick={onSend}
            disabled={modal.sending}
          >
            {modal.sending ? tCommon('sending') : tCommon('send')}
          </button>
        </div>
      </div>
    </div>
  )
}
