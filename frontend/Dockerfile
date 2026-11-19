# syntax=docker/dockerfile:1
# Review UI image: build the static files with Node, serve them with nginx.
#   docker build -t invoice-review-frontend frontend
# nginx also forwards /api/ to the backend service, so the browser talks to
# one origin and no CORS setting is needed.

FROM node:24.12.0-alpine@sha256:c921b97d4b74f51744057454b306b418cf693865e73b8100559189605f6955b8 AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY index.html vite.config.js ./
COPY src ./src
# "/" makes the UI call /api/... on its own origin (nginx proxies it).
ARG VITE_API_URL=/
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# nginx running as a non-root user (uid 101), listening on 8080.
FROM nginxinc/nginx-unprivileged:1.31.7-alpine@sha256:b5047b9b76845eac124358373c6852377c52e4b05834a47647e955dd91cb8f1e
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
