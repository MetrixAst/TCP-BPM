'use client'

import { Link } from '@/i18n/routing'

export default function MetriXBrandLogo({
  product = 'Invoice',
  className = "text-2xl font-medium tracking-tight font-['Helvetica_Neue']",
}: {
  product?: string
  className?: string
}) {
  return (
    <Link
      href="/"
      className={`${className} inline-flex items-baseline gap-[0.25em] no-underline hover:opacity-80 transition-opacity`}
      aria-label={`metriX ${product}`}
      onClick={() => window.dispatchEvent(new CustomEvent('resetToRegistry'))}
    >
      <img src="/metrix-logo.svg" alt="metriX" style={{ height: '0.7em' }} />
      {product ? <span className="text-[#262626]">{product}</span> : null}
    </Link>
  )
}
