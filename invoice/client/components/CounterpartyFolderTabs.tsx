'use client'

import { useTranslations } from 'next-intl'

interface CounterpartyFolder {
  id?: string
  fullName: string
}

interface CounterpartyFolderTabsProps {
  folders: CounterpartyFolder[]
  selected: string | null
  onSelect: (folderFullName: string | null) => void
}

/**
 * Выбор папки справочника Контрагенты (fullName группы из 1С).
 * null = все папки.
 */
export default function CounterpartyFolderTabs({
  folders,
  selected,
  onSelect,
}: CounterpartyFolderTabsProps) {
  const t = useTranslations('folders')
  const tCommon = useTranslations('common')
  if (folders.length === 0) return null

  const tabStyle = (active: boolean) => ({
    padding: '8px 14px',
    borderRadius: 8,
    border: active ? '1px solid #2563eb' : '1px solid #e5e7eb',
    background: active ? '#eff6ff' : '#fff',
    color: active ? '#1d4ed8' : '#374151',
    cursor: 'pointer' as const,
    fontSize: 14,
    fontWeight: active ? 600 : 500,
    whiteSpace: 'nowrap' as const,
  })

  return (
    <div
      className="row gap-4"
      style={{
        flexWrap: 'wrap',
        padding: '4px 0 12px',
        alignItems: 'center',
      }}
      role="tablist"
      aria-label={t('ariaLabel')}
    >
      <span style={{ fontSize: 13, color: '#6b7280', marginRight: 4 }}>{t('label')}</span>
      <button type="button" style={tabStyle(selected === null)} onClick={() => onSelect(null)}>
        {tCommon('all')}
      </button>
      {folders.map((folder) => (
        <button
          key={folder.id || folder.fullName}
          type="button"
          style={tabStyle(selected === folder.fullName)}
          onClick={() => onSelect(folder.fullName)}
          title={folder.fullName}
        >
          {folder.fullName}
        </button>
      ))}
    </div>
  )
}
