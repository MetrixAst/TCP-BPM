'use client'

import { useTranslations } from 'next-intl'
import { PaymentAnalytics } from '@/lib/api'
import MaskedIcon from './MaskedIcon'
import { metrixIcon } from '@/lib/metrixAssets'

type StatusFilterValue = 'paid' | 'partial' | 'unpaid' | 'overdue' | undefined

interface AnalyticsCardsProps {
  analytics: PaymentAnalytics
  activeStatus?: StatusFilterValue
  onSelectStatus?: (status: StatusFilterValue) => void
}

export default function AnalyticsCards({
  analytics,
  activeStatus,
  onSelectStatus,
}: AnalyticsCardsProps) {
  const t = useTranslations('analytics')
  const invoiceTotal = analytics.total_invoices ?? analytics.total_tenants
  const cards: {
    title: string
    subtitle: string
    value: string
    icon: string | null
    iconClass: string
    status: StatusFilterValue
  }[] = [
    {
      title: t('invoiceCount'),
      subtitle: t('invoiceCountSubtitle'),
      value: String(invoiceTotal),
      icon: metrixIcon('receipt-alt.svg'),
      iconClass: 'gray',
      status: undefined,
    },
    {
      title: t('paid'),
      subtitle: t('periodSubtitle'),
      value: t('invoicesCount', { count: analytics.paid }),
      icon: metrixIcon('check.svg'),
      iconClass: 'green',
      status: 'paid',
    },
    {
      title: t('partial'),
      subtitle: t('periodSubtitle'),
      value: t('invoicesCount', { count: analytics.partial ?? 0 }),
      icon: metrixIcon('circle-percentage.svg'),
      iconClass: 'blue',
      status: 'partial',
    },
    {
      title: t('unpaid'),
      subtitle: t('periodSubtitle'),
      value: t('invoicesCount', { count: analytics.unpaid }),
      icon: metrixIcon('circle-exclamation.svg'),
      iconClass: 'orange',
      status: 'unpaid',
    },
    {
      title: t('overdue'),
      subtitle: t('periodSubtitle'),
      value: t('invoicesCount', { count: analytics.overdue }),
      icon: metrixIcon('close.svg'),
      iconClass: 'red',
      status: 'overdue',
    },
  ]

  const clickable = Boolean(onSelectStatus)

  return (
    <div className="row gap-s stretch">
      {cards.map((card, index) => {
        const isActive = clickable && activeStatus === card.status
        return (
          <div
            key={index}
            className={`card flex${clickable ? ' cursor-pointer transition-shadow' : ''}${
              isActive ? ' ring-2 ring-blue-600 ring-inset' : ''
            }`}
            role={clickable ? 'button' : undefined}
            tabIndex={clickable ? 0 : undefined}
            aria-pressed={clickable ? isActive : undefined}
            onClick={
              clickable
                ? () => onSelectStatus!(isActive ? undefined : card.status)
                : undefined
            }
            onKeyDown={
              clickable
                ? (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSelectStatus!(isActive ? undefined : card.status)
                    }
                  }
                : undefined
            }
          >
            {card.icon && (
              <div className={`icon ${card.iconClass} float`}>
                <MaskedIcon icon={card.icon} />
              </div>
            )}
            <p className="title">{card.title}</p>
            <p className="subtitle">{card.subtitle}</p>
            <div className="rate">
              <p className="value">{card.value}</p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
