FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

ARG VITE_API_URL=/invoice-api
ENV VITE_API_URL=$VITE_API_URL
ARG VITE_BASE=/invoice-admin/
ENV VITE_BASE=$VITE_BASE

RUN npm run build

FROM nginx:1.27-alpine AS runner

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html/invoice-admin

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
