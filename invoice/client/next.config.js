/** @type {import('next').NextConfig} */
const basePath = (process.env.NEXT_BASE_PATH || '').replace(/\/$/, '')

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  ...(basePath ? { basePath } : {}),
  env: {
    API_URL: process.env.API_URL || 'http://localhost:8000',
  },
  async rewrites() {
    const backend = (
      process.env.API_BACKEND_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      'http://localhost:8004'
    ).replace(/\/$/, '')
    return [
      {
        source: '/api-proxy/:path*',
        destination: `${backend}/:path*`,
      },
    ]
  },
}

// Only use next-intl plugin if the package is installed
try {
  const createNextIntlPlugin = require('next-intl/plugin');
  const withNextIntl = createNextIntlPlugin('./i18n/request.ts');
  module.exports = withNextIntl(nextConfig);
} catch (e) {
  // If next-intl is not installed, use default config
  module.exports = nextConfig;
}
