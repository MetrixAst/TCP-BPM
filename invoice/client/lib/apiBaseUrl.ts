const LOCAL_FALLBACK = 'http://localhost:8004'

function configuredApiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || LOCAL_FALLBACK
}

/**
 * Базовый URL API для axios/fetch.
 * В браузере на проде — same-origin /api-proxy (Next.js rewrite → backend),
 * чтобы расширения Chrome не блокировали cross-origin на api.*.
 */
export function getApiBaseUrl(): string {
  const configured = configuredApiUrl()

  if (typeof window === 'undefined') {
    return configured
  }

  if (process.env.NEXT_PUBLIC_USE_API_PROXY === 'false') {
    return configured
  }

  const host = window.location.hostname
  if (host === 'localhost' || host === '127.0.0.1') {
    return configured
  }

  return '/api-proxy'
}

/** @deprecated */
export const API_URL = configuredApiUrl()
