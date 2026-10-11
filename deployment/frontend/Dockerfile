FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package*.json ./

RUN npm install

COPY frontend/ .
COPY frontend/.env .env

RUN npm run build


FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80