'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from '@/i18n/routing'
import { isPortalSession } from '@/lib/tenantContext'

const allowStaffWithoutLogin =
  process.env.NEXT_PUBLIC_ALLOW_STAFF_WITHOUT_LOGIN === 'true'

export default function TenantAuthGuard({ children }: { children: React.ReactNode }) {
  const t = useTranslations('common')
  const router = useRouter()
  const [allowed, setAllowed] = useState(allowStaffWithoutLogin)

  useEffect(() => {
    if (allowStaffWithoutLogin) {
      setAllowed(true)
      return
    }
    if (!isPortalSession()) {
      router.replace('/login')
      return
    }
    setAllowed(true)
  }, [router])

  if (!allowed) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-500">
        {t('loading')}
      </div>
    )
  }

  return <>{children}</>
}
