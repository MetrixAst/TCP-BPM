'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import type { Counterparty } from '@/lib/api'
import { paymentApi } from '@/lib/api'
import {
  DEFAULT_QUICK_MESSAGE_TEMPLATES,
  getQuickMessageTemplates,
  renderQuickMessageTemplate,
  resetQuickMessageTemplates,
  saveQuickMessageTemplates,
  type QuickMessageTemplate,
} from '@/lib/quickMessageTemplates'
import { useToast } from '@/lib/toastContext'
import { formatApiError } from '@/lib/notificationHelpers'

interface QuickMessageModalProps {
  counterparty: Counterparty
  phoneOptions: string[]
  onClose: () => void
}

export default function QuickMessageModal({
  counterparty,
  phoneOptions,
  onClose,
}: QuickMessageModalProps) {
  const t = useTranslations('quickMessage')
  const tCommon = useTranslations('common')
  const toast = useToast()

  const [templates, setTemplates] = useState<QuickMessageTemplate[]>(getQuickMessageTemplates())
  const [selectedId, setSelectedId] = useState<string>(templates[0]?.id || '')
  const [selectedPhone, setSelectedPhone] = useState(phoneOptions[0] || '')
  const [editing, setEditing] = useState(false)
  const [editedBody, setEditedBody] = useState('')
  const [messageText, setMessageText] = useState(() =>
    templates[0] ? renderQuickMessageTemplate(templates[0], counterparty.fullName) : '',
  )
  const [sending, setSending] = useState(false)

  const selectTemplate = (template: QuickMessageTemplate) => {
    setSelectedId(template.id)
    setEditing(false)
    setMessageText(renderQuickMessageTemplate(template, counterparty.fullName))
  }

  const startEditing = () => {
    const template = templates.find((tpl) => tpl.id === selectedId)
    if (!template) return
    setEditedBody(template.body)
    setEditing(true)
  }

  const saveTemplateEdit = () => {
    const next = templates.map((tpl) =>
      tpl.id === selectedId ? { ...tpl, body: editedBody } : tpl,
    )
    setTemplates(next)
    saveQuickMessageTemplates(next)
    setEditing(false)
    const updated = next.find((tpl) => tpl.id === selectedId)
    if (updated) setMessageText(renderQuickMessageTemplate(updated, counterparty.fullName))
  }

  const handleReset = () => {
    resetQuickMessageTemplates()
    setTemplates(DEFAULT_QUICK_MESSAGE_TEMPLATES)
    setSelectedId(DEFAULT_QUICK_MESSAGE_TEMPLATES[0].id)
    setEditing(false)
    setMessageText(
      renderQuickMessageTemplate(DEFAULT_QUICK_MESSAGE_TEMPLATES[0], counterparty.fullName),
    )
  }

  const handleSend = async () => {
    const phone = selectedPhone.trim()
    if (!phone) {
      toast(t('noPhone'), 'error')
      return
    }
    if (!counterparty.id) return
    setSending(true)
    try {
      const result = await paymentApi.sendQuickMessage(counterparty.id, phone, messageText)
      if (result.success) {
        toast(t('sentSuccess'), 'success')
        onClose()
      } else {
        toast(t('sentError', { error: result.error || '' }), 'error')
      }
    } catch (error: unknown) {
      toast(t('sentError', { error: formatApiError(error) }), 'error')
    } finally {
      setSending(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4"
      onClick={() => !sending && onClose()}
    >
      <div
        className="w-full max-w-md mx-card p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-gray-900">{t('title')}</h3>
        <p className="text-sm text-gray-600 mt-1">{counterparty.fullName}</p>

        <div className="mt-3 space-y-3">
          <div>
            <div className="text-sm text-gray-700 mb-1">{t('phoneLabel')}</div>
            <div className="space-y-1">
              {phoneOptions.map((phone) => (
                <label key={phone} className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="radio"
                    name="quick-msg-phone"
                    checked={selectedPhone === phone}
                    onChange={() => setSelectedPhone(phone)}
                    disabled={sending}
                  />
                  <span>{phone}</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <div className="text-sm text-gray-700 mb-1">{t('templateLabel')}</div>
            <div className="flex flex-wrap gap-2">
              {templates.map((template) => (
                <button
                  key={template.id}
                  type="button"
                  className={`px-3 py-1.5 text-sm rounded-lg border ${
                    selectedId === template.id
                      ? 'border-blue-600 bg-blue-50 text-blue-700'
                      : 'border-gray-300 text-gray-700'
                  }`}
                  onClick={() => selectTemplate(template)}
                  disabled={sending}
                >
                  {template.title}
                </button>
              ))}
            </div>
          </div>

          {editing ? (
            <div>
              <div className="text-sm text-gray-700 mb-1">{t('templateLabel')}</div>
              <textarea
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                rows={5}
                value={editedBody}
                onChange={(e) => setEditedBody(e.target.value)}
              />
              <div className="mt-2 flex gap-2 justify-end">
                <button
                  type="button"
                  className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 text-gray-700"
                  onClick={() => setEditing(false)}
                >
                  {t('cancelEdit')}
                </button>
                <button
                  type="button"
                  className="px-3 py-1.5 text-sm rounded-lg bg-blue-600 text-white"
                  onClick={saveTemplateEdit}
                >
                  {t('save')}
                </button>
              </div>
            </div>
          ) : (
            <div>
              <div className="text-sm text-gray-700 mb-1">{t('textLabel')}</div>
              <div className="flex gap-3 mb-1.5">
                <button
                  type="button"
                  className="text-xs text-blue-600 hover:underline"
                  onClick={startEditing}
                  disabled={sending}
                >
                  {t('edit')}
                </button>
                <button
                  type="button"
                  className="text-xs text-gray-500 hover:underline"
                  onClick={handleReset}
                  disabled={sending}
                >
                  {t('resetTemplates')}
                </button>
              </div>
              <textarea
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                rows={5}
                value={messageText}
                onChange={(e) => setMessageText(e.target.value)}
                disabled={sending}
              />
            </div>
          )}
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button
            className="px-3 py-2 text-sm rounded-lg border border-gray-300 text-gray-700"
            onClick={onClose}
            disabled={sending}
          >
            {tCommon('cancel')}
          </button>
          <button
            className="mx-btn-primary px-4"
            onClick={handleSend}
            disabled={sending || editing}
          >
            {sending ? t('sending') : t('send')}
          </button>
        </div>
      </div>
    </div>
  )
}
