import type { LucideIcon } from 'lucide-react'

export interface TabDef<T extends string> {
  key: T
  label: string
  icon: LucideIcon
}

interface TabsProps<T extends string> {
  tabs: TabDef<T>[]
  active: T
  onChange: (key: T) => void
}

export function Tabs<T extends string>({ tabs, active, onChange }: TabsProps<T>) {
  return (
    <div className="mb-6 border-b border-slate-100 overflow-x-auto">
      <div className="flex gap-6">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => onChange(tab.key)}
              className={`flex items-center gap-2 bg-transparent border-x-0 border-t-0 ${
                active === tab.key ? 'mx-tab-active' : 'mx-tab-inactive'
              }`}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
