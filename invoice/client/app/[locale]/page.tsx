import PaymentRegistry from '@/components/PaymentRegistry'
import TenantAuthGuard from '@/components/TenantAuthGuard'

export default function Home({
  params: { locale }
}: {
  params: { locale: string }
}) {
  return (
    <main className="mx-page">
      <TenantAuthGuard>
        <PaymentRegistry locale={locale} />
      </TenantAuthGuard>
    </main>
  )
}
