'use client'

import { useCallback, useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Counterparty, paymentApi } from '@/lib/api'
import CounterpartyBalance from './CounterpartyBalance'
import InvoicesList from './InvoicesList'
import CounterpartyNotifyModal from './CounterpartyNotifyModal'
import QuickMessageModal from './QuickMessageModal'
import { catalogApi } from '@/lib/catalogApi'
import { extractPhoneOptions } from '@/lib/counterpartyPhoneUtils'
import { formatApiError } from '@/lib/notificationHelpers'
import { useToast } from '@/lib/toastContext'
import { useCounterpartyNotify } from '@/lib/useCounterpartyNotify'
import { isPaymentTypeEnabled } from '@/lib/paymentTypesContext'
import { getEffectiveTenantId } from '@/lib/tenantContext'

interface CounterpartyDetailsProps {
  counterparty: Counterparty
  onClose?: () => void
}

export default function CounterpartyDetails({ counterparty, onClose }: CounterpartyDetailsProps) {
  const t = useTranslations('counterpartyDetails')
  const tCommon = useTranslations('common')
  const tQuickMessage = useTranslations('quickMessage')
  const toast = useToast()
  const [activeTab, setActiveTab] = useState<'details' | 'balance' | 'invoices' | 'processes'>('details')
  const [savedPhones, setSavedPhones] = useState<string[]>([])
  const [phoneRent, setPhoneRent] = useState('')
  const [phoneUtilities, setPhoneUtilities] = useState('')
  const [phoneOperations, setPhoneOperations] = useState('')
  const [savingRouting, setSavingRouting] = useState(false)
  const [addingPhone, setAddingPhone] = useState(false)
  const [newPhoneInput, setNewPhoneInput] = useState('')
  const [sendingAll, setSendingAll] = useState(false)
  const [showQuickMessage, setShowQuickMessage] = useState(false)
  const { notifyModal, setNotifyModal, openNotifyModal, handleSendFromModal } =
    useCounterpartyNotify()

  const phoneOptions = extractPhoneOptions(counterparty, savedPhones)

  const loadSavedPhones = useCallback(async () => {
    if (!getEffectiveTenantId() || !counterparty.id) {
      setSavedPhones([])
      return
    }
    try {
      const data = await catalogApi.getCounterpartyPhones(counterparty.id)
      setSavedPhones(data.phones)
      setPhoneRent(data.phone_rent || '')
      setPhoneUtilities(data.phone_utilities || '')
      setPhoneOperations(data.phone_operations || '')
    } catch (err) {
      console.warn('Failed to load counterparty phones', err)
      setSavedPhones([])
      setPhoneRent('')
      setPhoneUtilities('')
      setPhoneOperations('')
    }
  }, [counterparty.id])

  useEffect(() => {
    loadSavedPhones()
  }, [loadSavedPhones])

  const handleAddPhone = async () => {
    const value = newPhoneInput.trim()
    if (!value) return
    if (!getEffectiveTenantId()) {
      toast(t('selectTenantFirst'), 'error')
      return
    }
    setAddingPhone(true)
    try {
      const data = await catalogApi.appendCounterpartyPhone(
        counterparty.id,
        value,
        counterparty.fullName,
      )
      setSavedPhones(data.phones)
      setPhoneRent(data.phone_rent || '')
      setPhoneUtilities(data.phone_utilities || '')
      setPhoneOperations(data.phone_operations || '')
      setNewPhoneInput('')
    } catch (error: unknown) {
      toast(t('savePhoneFailed', { error: formatApiError(error) }), 'error')
    } finally {
      setAddingPhone(false)
    }
  }

  const handleSavePhoneRouting = async () => {
    if (!getEffectiveTenantId()) {
      toast(t('selectTenantFirst'), 'error')
      return
    }
    setSavingRouting(true)
    try {
      const data = await catalogApi.updateCounterpartyPhoneRouting(
        counterparty.id,
        {
          phone_rent: phoneRent || undefined,
          phone_utilities: phoneUtilities || undefined,
          phone_operations: phoneOperations || undefined,
        },
        counterparty.fullName,
      )
      setSavedPhones(data.phones)
      setPhoneRent(data.phone_rent || '')
      setPhoneUtilities(data.phone_utilities || '')
      setPhoneOperations(data.phone_operations || '')
    } catch (error: unknown) {
      toast(t('saveFailed', { error: formatApiError(error) }), 'error')
    } finally {
      setSavingRouting(false)
    }
  }

  const handleSendAllInvoices = async () => {
    if (!getEffectiveTenantId()) {
      toast(t('selectTenantFirst'), 'error')
      return
    }
    if (!counterparty.id) return
    setSendingAll(true)
    try {
      const now = new Date()
      const period = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
      // Тот же механизм, что у массовой рассылки должникам (/send-debtors),
      // просто сузили до одного контрагента — все его неоплаченные счета за
      // текущий месяц по всем найденным типам услуг, с той же защитой от
      // повторной отправки в тот же день.
      const result = await paymentApi.sendDebtorsBulk({
        period,
        counterpartyId: counterparty.id,
      })
      toast(result.message, result.errors ? 'error' : 'success')
    } catch (error: unknown) {
      toast(formatApiError(error), 'error')
    } finally {
      setSendingAll(false)
    }
  }

  return (
    <div className="bg-white rounded-lg shadow-lg">
      {/* Header */}
      <div className="border-b border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4">
            {onClose && (
              <button
                onClick={onClose}
                className="text-gray-500 hover:text-gray-700"
              >
                ←
              </button>
            )}
            <div>
              <div className="text-sm text-gray-500 mb-1">{t('breadcrumb', { name: counterparty.fullName })}</div>
              <h1 className="text-2xl font-bold">{counterparty.fullName}</h1>
            </div>
          </div>
        </div>

        {/* Basic Info */}
        <div className="grid grid-cols-3 gap-4 mt-4">
          <div>
            <div className="text-sm text-gray-500">{t('base')}</div>
            <div className="font-medium">{counterparty.counterpartyType || t('defaultBase')}</div>
          </div>
          <div>
            <div className="text-sm text-gray-500">{t('category')}</div>
            <div className="font-medium">{t('supplier')}</div>
          </div>
          <div>
            <div className="text-sm text-gray-500">{t('type')}</div>
            <div className="font-medium">
              {counterparty.govEntity ? t('govEntity') : t('legalEntity')}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 px-6">
        <div className="flex gap-6">
          <button
            onClick={() => setActiveTab('details')}
            className={`py-4 px-2 border-b-2 font-medium ${
              activeTab === 'details'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t('tabs.details')}
          </button>
          <button
            onClick={() => setActiveTab('invoices')}
            className={`py-4 px-2 border-b-2 font-medium ${
              activeTab === 'invoices'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t('tabs.invoices')}
          </button>
          <button
            onClick={() => setActiveTab('balance')}
            className={`py-4 px-2 border-b-2 font-medium ${
              activeTab === 'balance'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t('tabs.balance')}
          </button>
          <button
            onClick={() => setActiveTab('processes')}
            className={`py-4 px-2 border-b-2 font-medium ${
              activeTab === 'processes'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t('tabs.processes')}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {activeTab === 'details' && (
          <div className="grid grid-cols-3 gap-6">
            {/* Left Column - Main Details */}
            <div className="col-span-2 space-y-6">
              {/* Messages Section */}
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <span className="font-semibold">{t('messages')}</span>
                    <span className="text-gray-500 ml-2">{t('letters')}</span>
                  </div>
                </div>
                <div className="text-center py-8 text-gray-400">
                   {t('noMessages')}
                </div>
                <div className="flex gap-2 mt-4">
                  <input
                    type="text"
                    placeholder={t('messagePlaceholder')}
                    className="flex-1 px-4 py-2 border border-gray-300 rounded-lg"
                  />
                  <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                    {tCommon('send')}
                  </button>
                </div>
              </div>
            </div>

            {/* Right Column - Sidebar */}
            <div className="space-y-4">
              {/* Телефоны */}
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-semibold">{t('phones')}</h3>
                  <button
                    type="button"
                    className="text-blue-600 hover:text-blue-800 text-lg leading-none"
                    title={t('addPhoneTitle')}
                    onClick={() => {
                      setNewPhoneInput('')
                      const el = document.getElementById('cp-new-phone-input')
                      el?.focus()
                    }}
                  >
                    +
                  </button>
                </div>
                {phoneOptions.length > 0 ? (
                  <ul className="space-y-1">
                    {phoneOptions.map((phone) => (
                      <li key={phone}>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            openNotifyModal(counterparty, phoneOptions, phone)
                          }}
                          className="text-sm text-blue-600 hover:text-blue-800 hover:underline cursor-pointer"
                        >
                          {phone}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-sm text-gray-400">{t('noPhones')}</div>
                )}
                <div className="mt-2 flex gap-2">
                  <input
                    id="cp-new-phone-input"
                    type="tel"
                    className="flex-1 border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
                    placeholder={t('phonePlaceholder')}
                    value={newPhoneInput}
                    onChange={(e) => setNewPhoneInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleAddPhone()
                    }}
                    disabled={addingPhone}
                  />
                  <button
                    type="button"
                    className="px-2 py-1.5 text-sm rounded-lg border border-blue-300 text-blue-700 disabled:opacity-50"
                    onClick={handleAddPhone}
                    disabled={addingPhone || !newPhoneInput.trim()}
                  >
                    {addingPhone ? '…' : 'OK'}
                  </button>
                </div>
                {phoneOptions.length >= 1 && (
                  <div className="mt-3 pt-3 border-t border-gray-200 space-y-2">
                    <p className="text-xs text-gray-500">
                      {t('autoSendHint')}
                    </p>
                    {isPaymentTypeEnabled('rent') && (
                    <label className="block text-xs text-gray-600">
                      {tCommon('serviceTypes.rent')}
                      <select
                        className="mt-0.5 w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm"
                        value={phoneRent}
                        onChange={(e) => setPhoneRent(e.target.value)}
                      >
                        <option value="">{t('notSelected')}</option>
                        {phoneOptions.map((p) => (
                          <option key={`rent-${p}`} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                    </label>
                    )}
                    {isPaymentTypeEnabled('utilities') && (
                    <label className="block text-xs text-gray-600">
                      {tCommon('serviceTypes.utilities')}
                      <select
                        className="mt-0.5 w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm"
                        value={phoneUtilities}
                        onChange={(e) => setPhoneUtilities(e.target.value)}
                      >
                        <option value="">{t('notSelected')}</option>
                        {phoneOptions.map((p) => (
                          <option key={`util-${p}`} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                    </label>
                    )}
                    {isPaymentTypeEnabled('operations') && (
                    <label className="block text-xs text-gray-600">
                      {tCommon('serviceTypes.operations')}
                      <select
                        className="mt-0.5 w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm"
                        value={phoneOperations}
                        onChange={(e) => setPhoneOperations(e.target.value)}
                      >
                        <option value="">{t('notSelected')}</option>
                        {phoneOptions.map((p) => (
                          <option key={`ops-${p}`} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                    </label>
                    )}
                    <button
                      type="button"
                      className="w-full text-sm py-1.5 rounded-lg bg-blue-600 text-white disabled:opacity-50"
                      onClick={handleSavePhoneRouting}
                      disabled={savingRouting}
                    >
                      {savingRouting ? tCommon('saving') : t('saveRouting')}
                    </button>
                  </div>
                )}
                {phoneOptions.length > 0 && (
                  <button
                    type="button"
                    className="mt-2 w-full text-sm py-1.5 rounded-lg border border-blue-300 text-blue-700 disabled:opacity-50"
                    onClick={handleSendAllInvoices}
                    disabled={sendingAll}
                  >
                    {sendingAll ? t('sendAllInvoicesSending') : t('sendAllInvoices')}
                  </button>
                )}
                {phoneOptions.length > 0 && (
                  <button
                    type="button"
                    className="mt-2 w-full text-sm py-1.5 rounded-lg border border-gray-300 text-gray-700"
                    onClick={() => setShowQuickMessage(true)}
                  >
                    {tQuickMessage('buttonLabel')}
                  </button>
                )}
              </div>

              {/* Почта */}
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-semibold">{t('mail')}</h3>
                  <button className="text-blue-600">+</button>
                </div>
                {counterparty.email ? (
                  <div className="text-sm">{counterparty.email}</div>
                ) : (
                  <div className="text-sm text-gray-400">{t('noEmail')}</div>
                )}
              </div>

              {/* Ссылки */}
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-semibold">{t('links')}</h3>
                  <button className="text-blue-600">+</button>
                </div>
                {counterparty.website ? (
                  <a href={counterparty.website} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 hover:underline">
                    {counterparty.website}
                  </a>
                ) : (
                  <div className="text-sm text-gray-400">{t('noLinks')}</div>
                )}
              </div>

              {/* Адреса */}
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-semibold">{t('addresses')}</h3>
                  <button className="text-blue-600">+</button>
                </div>
                {counterparty.address ? (
                  <div className="text-sm">{counterparty.address}</div>
                ) : (
                  <div className="text-sm text-gray-400">{t('noAddresses')}</div>
                )}
              </div>

              {/* Дополнительно */}
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-semibold">{t('additional')}</h3>
                </div>
                <div className="space-y-2 text-sm">
                  {counterparty.iin && (
                    <div>
                      <span className="text-gray-500">{t('iin')}</span> {counterparty.iin}
                    </div>
                  )}
                  {counterparty.bin && (
                    <div>
                      <span className="text-gray-500">{t('bin')}</span> {counterparty.bin}
                    </div>
                  )}
                  {counterparty.rnn && (
                    <div>
                      <span className="text-gray-500">{t('rnn')}</span> {counterparty.rnn}
                    </div>
                  )}
                  {counterparty.kbe && (
                    <div>
                      <span className="text-gray-500">{t('kbe')}</span> {counterparty.kbe}
                    </div>
                  )}
                  {counterparty.vatCertNo && (
                    <div>
                      <span className="text-gray-500">{t('vatCertNo')}</span> {counterparty.vatCertNo}
                    </div>
                  )}
                  {counterparty.vatCertDate && (
                    <div>
                      <span className="text-gray-500">{t('vatCertDate')}</span> {counterparty.vatCertDate}
                    </div>
                  )}
                  {counterparty.residencyCountry && (
                    <div>
                      <span className="text-gray-500">{t('residencyCountry')}</span> {counterparty.residencyCountry}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'invoices' && (
          <InvoicesList counterpartyId={counterparty.id} />
        )}

        {activeTab === 'balance' && (
          <CounterpartyBalance
            counterpartyId={counterparty.id}
            counterpartyName={counterparty.fullName}
          />
        )}

        {activeTab === 'processes' && (
          <div className="text-center py-8 text-gray-500">
            {t('processesEmpty')}
          </div>
        )}
      </div>

      {notifyModal && (
        <CounterpartyNotifyModal
          modal={notifyModal}
          onClose={() => !notifyModal.sending && setNotifyModal(null)}
          onChange={setNotifyModal}
          onSend={handleSendFromModal}
        />
      )}

      {showQuickMessage && (
        <QuickMessageModal
          counterparty={counterparty}
          phoneOptions={phoneOptions}
          onClose={() => setShowQuickMessage(false)}
        />
      )}
    </div>
  )
}
