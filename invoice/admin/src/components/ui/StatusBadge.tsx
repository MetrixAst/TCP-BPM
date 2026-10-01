export type BadgeStatus = 'ok' | 'would_write' | 'empty_skip' | 'fail'

const STATUS_LABEL: Record<BadgeStatus, string> = {
  ok: 'Записано',
  would_write: 'Будет записано',
  empty_skip: 'Нет телефона',
  fail: 'Ошибка',
}

const STATUS_CLASS: Record<BadgeStatus, string> = {
  ok: 'mx-badge-paid',
  would_write: 'mx-badge-partial',
  empty_skip: 'mx-badge-neutral',
  fail: 'mx-badge-overdue',
}

export function StatusBadge({ status }: { status: BadgeStatus }) {
  return <span className={STATUS_CLASS[status]}>{STATUS_LABEL[status]}</span>
}

export function BoolBadge({ trueLabel, falseLabel, value }: { trueLabel: string; falseLabel: string; value: boolean }) {
  return (
    <span className={value ? 'mx-badge-paid' : 'mx-badge-neutral'}>{value ? trueLabel : falseLabel}</span>
  )
}
