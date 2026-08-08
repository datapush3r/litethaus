FROM node:22-slim AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

ARG DOCKER_CLI_VERSION=27.3.1
ARG COMPOSE_VERSION=v2.29.7
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz" | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && mkdir -p /usr/local/lib/docker/cli-plugins \
    && curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" -o /usr/local/lib/docker/cli-plugins/docker-compose \
    && chmod +x /usr/local/lib/docker/cli-plugins/docker-compose \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Stays root (unlike caddy/Dockerfile's non-root user) - this container is
# handed /var/run/docker.sock, and socket access is root-equivalent on the
# host regardless of the container's own UID. A non-root UID here would need
# to match the host docker group's GID (host-specific, breaks across
# machines) without adding any real isolation, since the socket itself is
# the actual privilege boundary. Hardened instead at the compose level:
# read-only rootfs, cap_drop: ALL, no-new-privileges.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=frontend-build /app/dist ./static

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
