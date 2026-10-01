# invoice-client

Tenant-facing payment/invoice portal for Metrix TRC (shopping mall) tenants
— view invoices synced from 1C, download the formal invoice PDF, check
payment status. Localized in Russian, Kazakh, and English.

## Stack

Next.js 14 (App Router) + TypeScript, Tailwind CSS, `next-intl` for i18n.
Talks to `invoice-backend` over its REST API.

## Run locally

Requires `invoice-backend` running (default `http://localhost:8004`).

```bash
npm install
npm run dev
```

Opens on `http://localhost:3003`.

`NEXT_PUBLIC_API_URL` (see `.env.development`) controls which backend it
talks to — defaults to `http://localhost:8004` locally.

## i18n

Locale is routed via URL: `/ru`, `/kz`, `/en` (default redirect from `/` is
`/ru`). Translation files live in `messages/{ru,kz,en}.json`; see
`I18N_SETUP.md` for how to add new keys.

## Other scripts

```bash
npm run build   # production build
npm start       # serve the production build, port 3003
npm run lint
```

## Docker

```bash
docker build -t invoice-client .
```
