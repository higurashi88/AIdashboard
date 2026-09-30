FROM node:22-alpine AS development

WORKDIR /app
COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .

FROM development AS build
RUN test -f src/api/schema.d.ts || (echo "Run 'npm run generate:api' before building." >&2; exit 1)
RUN npm run build

FROM nginx:1.27-alpine AS production
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1
