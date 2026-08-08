FROM caddy:2-builder AS builder

RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare

FROM caddy:2

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

# Pre-chown the dirs the named volumes mount over - Docker seeds a fresh
# named volume's ownership from the image path's ownership at first mount,
# so this has to happen before the volume attaches. Paired with `user:` +
# `cap_add: NET_BIND_SERVICE` in the compose files, which let this non-root
# UID still bind :80/:443 without setcap.
RUN mkdir -p /data /config && chown -R 1000:1000 /data /config

USER 1000:1000
