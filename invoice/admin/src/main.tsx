import React from 'react'
import ReactDOM from 'react-dom/client'
import * as Sentry from '@sentry/react'
import App from './App'
import { ToastProvider } from './lib/toast'
import './styles.css'

if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0.1,
  })
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Sentry.ErrorBoundary
      fallback={
        <div style={{ padding: 24, fontFamily: 'sans-serif' }}>
          Что-то сломалось. Обновите страницу — если повторится, сообщите
          разработчику.
        </div>
      }
    >
      <ToastProvider>
        <App />
      </ToastProvider>
    </Sentry.ErrorBoundary>
  </React.StrictMode>,
)
