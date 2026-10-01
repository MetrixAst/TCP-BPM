'use client'

import { useCallback, useEffect, useState } from 'react'

export function useToggleDropdown() {
  const [openId, setOpenId] = useState<string | null>(null)

  useEffect(() => {
    if (!openId) return
    const close = (event: MouseEvent) => {
      const target = event.target
      if (target instanceof Element && target.closest('.toggle_handler')) {
        return
      }
      setOpenId(null)
    }
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [openId])

  const toggle = useCallback(
    (id: string) => (e: React.MouseEvent) => {
      e.stopPropagation()
      setOpenId((prev) => (prev === id ? null : id))
    },
    [],
  )

  const isOpen = useCallback((id: string) => openId === id, [openId])

  const close = useCallback(() => setOpenId(null), [])

  return { toggle, isOpen, close }
}
