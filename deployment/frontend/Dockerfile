FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package*.json ./

RUN npm ci

COPY frontend/ .

ARG VITE_BACKEND_HOST=http://localhost:8000
ARG VITE_API_STR=/api
ARG VITE_WS_URL=ws://localhost:8000/ws/telemetry

RUN npm run build


FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY deployment/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
