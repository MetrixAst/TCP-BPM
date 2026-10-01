'use client'

import { Payment } from '@/lib/api'
import { format, type Locale } from 'date-fns'
import { ru, kk, enUS } from 'date-fns/locale'
import NotificationPopover from './NotificationPopover'
import { ChevronLeft, ChevronRight } from 'lucide-react'

interface PaymentTableProps {
  payments: Payment[]
  loading: boolean
  currentPage: number
  totalPages: number
  onPageChange: (page: number) => void
  locale: string
}

const localeMap: Record<string, Locale> = {
  ru: ru,
  kz: kk,
  en: enUS,
}

export default function PaymentTable({
  payments,
  loading,
  currentPage,
  totalPages,
  onPageChange,
  locale,
}: PaymentTableProps) {
  const currentLocale = localeMap[locale] || ru
  const getStatusBadge = (status: string) => {
    const styles = {
      paid: 'mx-badge-paid',
      unpaid: 'mx-badge-unpaid',
      overdue: 'mx-badge-overdue',
    }

    const labels = {
      paid: 'Оплачено',
      unpaid: 'Не оплачено',
      overdue: 'Просрочено',
    }

    return (
      <span className={styles[status as keyof typeof styles] || 'mx-badge-unpaid'}>
        {labels[status as keyof typeof labels] || status}
      </span>
    )
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-'
    try {
      return format(new Date(dateString), 'dd.MM.yyyy', { locale: currentLocale })
    } catch {
      return dateString
    }
  }

  const renderPagination = () => {
    const pages = []
    const maxVisible = 5

    if (totalPages <= maxVisible) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i)
      }
    } else {
      if (currentPage <= 3) {
        for (let i = 1; i <= 3; i++) pages.push(i)
        pages.push('...')
        pages.push(totalPages - 1, totalPages)
      } else if (currentPage >= totalPages - 2) {
        pages.push(1, 2)
        pages.push('...')
        for (let i = totalPages - 2; i <= totalPages; i++) pages.push(i)
      } else {
        pages.push(1, 2)
        pages.push('...')
        pages.push(currentPage - 1, currentPage, currentPage + 1)
        pages.push('...')
        pages.push(totalPages - 1, totalPages)
      }
    }

    return pages
  }

  if (loading) {
    return (
      <div className="mx-card p-8 text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
        <p className="mt-4 text-gray-600">Загрузка данных...</p>
      </div>
    )
  }

  return (
    <div className="mx-card overflow-hidden">
      <div className="mx-card-header">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Статус платежей</h2>
          {payments.length > 0 && (
            <p className="text-sm text-slate-500 mt-0.5">
              За {format(new Date(payments[0].period + '-01'), 'MMMM yyyy', { locale: currentLocale })}
            </p>
          )}
        </div>
        <input type="text" placeholder="Поиск арендаторов" className="mx-input w-64" />
      </div>

      <div className="overflow-x-auto w-full">
        <table className="min-w-[1100px] w-full table-auto">
          <thead className="mx-table-head">
            <tr>
              <th className="mx-table-th">
                ИП
              </th>
              <th className="mx-table-th">
                Арендатор
              </th>
              <th className="mx-table-th">
                Уведомления
              </th>
              <th className="mx-table-th">
                Дата выставления счета
              </th>
              <th className="mx-table-th">
                Крайний срок оплаты
              </th>
              <th className="mx-table-th">
                Статус оплаты
              </th>
              <th className="mx-table-th">
                Дата оплаты
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-slate-100">
            {payments.map((payment) => (
              <tr key={payment.id} className="hover:bg-slate-50/60">
                <td
                  className="mx-table-td min-w-[200px] max-w-[360px] whitespace-normal break-words text-slate-900"
                  title={payment.ip_name}
                >
                  {payment.ip_name}
                </td>
                <td
                  className="mx-table-td min-w-[200px] max-w-[360px] whitespace-normal break-words text-slate-900"
                  title={payment.tenant_name}
                >
                  {payment.tenant_name}
                </td>
                <td className="mx-table-td whitespace-nowrap">
                  <NotificationPopover payment={payment} />
                </td>
                <td className="mx-table-td whitespace-nowrap text-slate-500">
                  {formatDate(payment.invoice_date)}
                </td>
                <td className="mx-table-td whitespace-nowrap text-slate-500">
                  До 5-го числа
                </td>
                <td className="mx-table-td whitespace-nowrap">
                  {getStatusBadge(payment.status)}
                </td>
                <td className="mx-table-td whitespace-nowrap text-slate-500">
                  {formatDate(payment.paid_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-end gap-1">
          <button
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1}
            className="mx-pagination-item disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ChevronLeft size={18} />
          </button>

          {renderPagination().map((page, index) => {
            if (page === '...') {
              return (
                <span key={`ellipsis-${index}`} className="px-2 text-slate-400 text-sm">
                  ...
                </span>
              )
            }

            return (
              <button
                key={page}
                type="button"
                onClick={() => onPageChange(page as number)}
                className={
                  currentPage === page ? 'mx-pagination-active' : 'mx-pagination-item'
                }
              >
                {page}
              </button>
            )
          })}

          <button
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
            className="mx-pagination-item disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ChevronRight size={20} />
          </button>
        </div>
      )}
    </div>
  )
}
