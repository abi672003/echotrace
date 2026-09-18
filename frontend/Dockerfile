# Build stage: compile the React app.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Empty by default so the app calls same-origin `/api/...` paths, which
# nginx below reverse-proxies to the backend service — avoids CORS
# entirely in production. Override at build time for a split-origin setup.
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

# Serve stage: static files + reverse proxy to the backend.
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
