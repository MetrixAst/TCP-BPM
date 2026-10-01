'use client'

import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'

type ToastKind = 'info' | 'success' | 'error'

interface ToastItem {
  id: number
  message: string
  kind: ToastKind
}

type ShowToast = (message: string, kind?: ToastKind) => void

const ToastContext = createContext<ShowToast | null>(null)

const KIND_STYLES: Record<ToastKind, string> = {
  info: 'bg-slate-800',
  success: 'bg-green-600',
  error: 'bg-red-600',
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const t = useTranslations('common')
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const idRef = useRef(0)

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const showToast = useCallback<ShowToast>(
    (message, kind = 'info') => {
      const id = ++idRef.current
      setToasts((prev) => [...prev, { id, message, kind }])
      window.setTimeout(() => dismiss(id), 6000)
    },
    [dismiss],
  )

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      <div className="fixed top-4 right-4 z-[9999] flex w-full max-w-sm flex-col gap-2 pointer-events-none">
        {toasts.map((item) => (
          <div
            key={item.id}
            className={`pointer-events-auto flex items-start gap-3 rounded-lg p-4 text-sm text-white shadow-lg ${KIND_STYLES[item.kind]}`}
          >
            <div className="flex-1 whitespace-pre-line">{item.message}</div>
            <button
              type="button"
              onClick={() => dismiss(item.id)}
              className="shrink-0 opacity-80 hover:opacity-100"
              aria-label={t('close')}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ShowToast {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return ctx
}
