'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { useRouter, usePathname } from '@/i18n/routing'
import { catalogApi, CatalogTRC } from '@/lib/catalogApi'
import {
  getEffectiveTrcId,
  getSelectedTrcId,
  isPortalSession,
  notifyTenantContextChanged,
  setSelectedTenantId,
  setSelectedTrcId,
} from '@/lib/tenantContext'
import { getPortalSession, redirectToLogin, refreshPortalSession } from '@/lib/tenantAuth'
import { Link } from '@/i18n/routing'
import MetriXBrandLogo from './MetriXBrandLogo'
import MaskedIcon from './MaskedIcon'
import { metrixIcon } from '@/lib/metrixAssets'
import { useToggleDropdown } from '@/hooks/useToggleDropdown'

interface HeaderProps {
  locale: string
}

export default function Header({ locale }: HeaderProps) {
  const t = useTranslations('header')
  const tPortal = useTranslations('tenantPortal')
  const router = useRouter()
  const pathname = usePathname()
  const [trcs, setTrcs] = useState<CatalogTRC[]>([])
  const [trcId, setTrcId] = useState<number | null>(getEffectiveTrcId())
  const [portalMode, setPortalMode] = useState(false)
  const [portalSession, setPortalSession] = useState(getPortalSession())
  const { toggle, isOpen, close } = useToggleDropdown()

  useEffect(() => {
    const sync = () => {
      setPortalMode(isPortalSession())
      setPortalSession(getPortalSession())
      setTrcId(getEffectiveTrcId())
    }
    sync()
    void refreshPortalSession().then(() => sync())
    window.addEventListener('tenantPortalAuthChanged', sync)
    return () => window.removeEventListener('tenantPortalAuthChanged', sync)
  }, [])

  useEffect(() => {
    if (portalMode) return
    catalogApi.listTrcs().then((data) => {
      setTrcs(data)
      const saved = getSelectedTrcId()
      const initial = saved && data.some((trc) => trc.id === saved) ? saved : data[0]?.id ?? null
      setTrcId(initial)
      if (initial) {
        setSelectedTrcId(initial)
        notifyTenantContextChanged()
      }
    })
  }, [portalMode])

  const changeLocale = (newLocale: string) => {
    router.replace(pathname, { locale: newLocale })
  }

  const selectedTrc = trcs.find((trc) => trc.id === trcId)

  const selectTrc = (id: number) => {
    setTrcId(id)
    setSelectedTrcId(id)
    notifyTenantContextChanged()
    close()
  }

  const handlePortalLogout = () => {
    close()
    setSelectedTrcId(null)
    setSelectedTenantId(null)
    notifyTenantContextChanged()
    redirectToLogin()
  }

  const portalDisplayName = portalSession
    ? portalSession.role === 'trc'
      ? portalSession.trc_name
      : portalSession.tenant_name
    : ''
  const portalSubtitle = portalSession
    ? (portalSession.role === 'trc' ? tPortal('trcAdmin') : portalSession.legal_name) +
      (portalSession.trc_name && portalSession.role !== 'trc'
        ? tPortal('trcSuffix', { trc: portalSession.trc_name })
        : '')
    : ''

  return (
    <header>
      <div className="container">
        <div className="logo as_side">
          <MetriXBrandLogo />
        </div>

        <div className="basic_info" />

        <div className="profile_items">
          {portalMode && portalSession ? (
            <div className="togglers single">
              <div
                className={`toggler_item fill toggle_handler toggle_parent${isOpen('portal_menu') ? ' opened' : ''}`}
                onClick={toggle('portal_menu')}
              >
                {portalDisplayName}
                <div
                  className={`toggle_content from_right auto_dismiss${isOpen('portal_menu') ? ' is-open' : ''}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="info_item without_bg" style={{ cursor: 'default' }}>
                    <div className="values">
                      <p className="value">{portalDisplayName}</p>
                      <p className="title">{portalSubtitle}</p>
                    </div>
                  </div>
                  <div className="info_item select_item" onClick={handlePortalLogout}>
                    <div className="values">
                      <p className="value" style={{ color: '#dc2626' }}>
                        {tPortal('logout')}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="togglers">
              <div
                className={`toggler_item fill toggle_handler toggle_parent${isOpen('select_trc') ? ' opened' : ''}`}
                onClick={toggle('select_trc')}
              >
                {selectedTrc?.name || t('trcFallback')}
                <div
                  className={`toggle_content auto_dismiss${isOpen('select_trc') ? ' is-open' : ''}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  <p className="section_title">{t('trcSectionTitle')}</p>
                  {trcs.length === 0 && (
                    <div className="info_item">
                      <div className="values">
                        <p className="value">{t('noTrc')}</p>
                      </div>
                    </div>
                  )}
                  {trcs.map((trc) => (
                    <div
                      key={trc.id}
                      className="info_item select_item"
                      onClick={() => selectTrc(trc.id)}
                    >
                      <div className="values">
                        <p className="value">{trc.name}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="toggler_item toggle_handler">{t('timezone')}</div>

              <Link href="/login" className="toggler_item hidden sm:inline">
                {t('tenantLogin')}
              </Link>
            </div>
          )}

          <div className="lang">
            
            <ul>
              <li
                className={locale === 'ru' ? 'active' : ''}
                onClick={() => locale !== 'ru' && changeLocale('ru')}
                role="button"
                tabIndex={0}
              >
                {t('languages.ru')}
              </li>
              <li
                className={locale === 'kz' ? 'active' : ''}
                onClick={() => locale !== 'kz' && changeLocale('kz')}
                role="button"
                tabIndex={0}
              >
                {t('languages.kz')}
              </li>
              <li
                className={locale === 'en' ? 'active' : ''}
                onClick={() => locale !== 'en' && changeLocale('en')}
                role="button"
                tabIndex={0}
              >
                {t('languages.en')}
              </li>
            </ul>
          </div>
        </div>
      </div>
    </header>
  )
}
