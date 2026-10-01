# invoice-admin

Admin panel for Metrix TRC (shopping mall) staff — manage tenants, review
synced 1C invoices/payments, configure per-tenant 1C/WhatsApp settings,
upload signature/stamp for invoice PDFs, and trigger bulk debtor
notifications.

## Stack

Vite + React 18 + TypeScript, Tailwind CSS. Talks to `invoice-backend` over
its REST API (`src/api.ts`).

## Run locally

Requires `invoice-backend` running (default `http://localhost:8004`).

```bash
npm install
npm run dev
```

Opens on `http://localhost:5173`.

`VITE_API_URL` (see `.env.development` / `.env.example`) controls which
backend it talks to — defaults to `http://localhost:8004` locally.

## Login

Use the `SUPER_ADMIN_USERNAME` / `SUPER_ADMIN_PASSWORD` configured in the
backend's `.env` (see `invoice-backend/.env.example`) — there's no
credential fixed in this repo.

## Other scripts

```bash
npm run build     # tsc + vite build
npm run preview   # serve the production build, port 5173
npm test          # vitest run
```

## Docker

```bash
docker build -t invoice-admin .
```

Builds the static bundle and serves it via nginx (`nginx.conf`).
