'use client'

import { useTranslations } from 'next-intl'

interface TabRefreshButtonProps {
  onClick: () => void
  loading?: boolean
  label?: string
}

export default function TabRefreshButton({
  onClick,
  loading = false,
  label,
}: TabRefreshButtonProps) {
  const t = useTranslations('tabRefresh')
  return (
    <button type="button" onClick={onClick} disabled={loading} className="button size-m">
      {loading ? t('refreshing') : label ?? t('default')}
    </button>
  )
}
