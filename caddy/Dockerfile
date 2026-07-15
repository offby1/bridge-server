# Custom Caddy image: caddy-docker-proxy (label-driven config, like the stock
# lucaslorentz/caddy-docker-proxy image) PLUS the caddy-ratelimit plugin, which
# is not in any stock Caddy build.
FROM caddy:2-builder AS builder
RUN xcaddy build \
    --with github.com/lucaslorentz/caddy-docker-proxy/v2 \
    --with github.com/mholt/caddy-ratelimit

FROM caddy:2-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
# Bake the base Caddyfile into the image rather than bind-mounting it. Bind
# mounts resolve on the Docker *daemon's* filesystem, so a repo path like
# ./caddy/Caddyfile is absent when deploying over a remote context (mini, hetz)
# and the mount fails. Baking it in makes the image self-contained everywhere.
COPY Caddyfile /etc/caddy/Caddyfile
# Run caddy-docker-proxy mode. Set ENTRYPOINT + CMD explicitly instead of
# relying on the base image's entrypoint: a bare CMD ["docker-proxy"] gets
# exec'd literally ("executable not found") because the base entrypoint isn't
# `caddy`. This makes argv unambiguously `caddy docker-proxy`.
ENTRYPOINT ["caddy"]
CMD ["docker-proxy"]
