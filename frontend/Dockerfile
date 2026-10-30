# Stages:
#   deps  -> node_modules from the lockfile
#   dev   -> Vite dev server with HMR; compose bind-mounts src/
#   build -> production bundle
#   prod  -> nginx serving dist/ and proxying /api to the backend

FROM node:24-alpine AS deps
ENV NPM_CONFIG_UPDATE_NOTIFIER=false
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]

FROM deps AS build
COPY . .
RUN npm run build

FROM nginx:1.29-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# Only API_UPSTREAM is substituted, so nginx's own $variables survive envsubst.
ENV NGINX_ENVSUBST_FILTER=API_UPSTREAM \
    API_UPSTREAM=http://backend:8000
EXPOSE 80
