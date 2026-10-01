'use client'

import { useCallback, useEffect, useRef, useState } from 'react'


export function useOneCDataLoad(
  loadFn: () => Promise<void>,
  cacheResetKey?: number,
) {
  const mountedLoadDone = useRef(false)
  const lastResetKey = useRef(cacheResetKey)
  const [loading, setLoading] = useState(false)
  const [refreshTick, setRefreshTick] = useState(0)

  const execute = useCallback(async () => {
    setLoading(true)
    try {
      await loadFn()
    } finally {
      setLoading(false)
    }
  }, [loadFn])

  useEffect(() => {
    if (!mountedLoadDone.current) {
      mountedLoadDone.current = true
      void execute()
    }
  }, [execute])

  useEffect(() => {
    if (cacheResetKey === undefined) return
    if (lastResetKey.current === cacheResetKey) return
    lastResetKey.current = cacheResetKey
    void execute()
  }, [cacheResetKey, execute])

  useEffect(() => {
    if (refreshTick === 0) return
    void execute()
  }, [refreshTick, execute])

  const refresh = useCallback(() => {
    setRefreshTick((n) => n + 1)
  }, [])

  return { loading, refresh }
}
