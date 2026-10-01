import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

type ToastKind = 'info' | 'success' | 'error'

interface ToastItem {
  id: number
  message: string
  kind: ToastKind
}

const KIND_STYLES: Record<ToastKind, string> = {
  info: 'bg-slate-800',
  success: 'bg-green-600',
  error: 'bg-red-600',
}

type ShowToast = (message: string, kind?: ToastKind) => void

const ToastContext = createContext<ShowToast | null>(null)

let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const showToast = useCallback<ShowToast>(
    (message, kind = 'info') => {
      const id = nextId++
      setToasts((prev) => [...prev, { id, message, kind }])
      window.setTimeout(() => dismiss(id), 6000)
    },
    [dismiss],
  )

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      <div className="fixed top-4 right-4 z-[9999] flex w-full max-w-sm flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-start gap-3 rounded-lg p-4 text-sm text-white shadow-lg whitespace-pre-line ${KIND_STYLES[t.kind]}`}
          >
            <div className="flex-1">{t.message}</div>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              className="shrink-0 opacity-80 hover:opacity-100"
              aria-label="Закрыть"
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
    throw new Error('useToast must be used within a ToastProvider')
  }
  return ctx
}
