// This layout is only used for the root path
// Middleware will handle locale routing
export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}

