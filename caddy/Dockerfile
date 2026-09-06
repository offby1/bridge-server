# This is a custom Caddy image. It provides caddy-docker-proxy, which gives the
# label-driven configuration that the stock lucaslorentz/caddy-docker-proxy image
# does, plus two plugins that are in no stock Caddy build: caddy-ratelimit and the
# CrowdSec bouncer.
#
# We ask for only the bouncer's `http` module. The same repository also publishes
# `appsec` and `layer4` modules, and we want neither: AppSec is out of scope (see
# docs/perf/crowdsec-plan.md) and `layer4` would drag in caddy-l4 for no reason.
FROM caddy:2-builder AS builder
RUN xcaddy build \
    --with github.com/lucaslorentz/caddy-docker-proxy/v2 \
    --with github.com/mholt/caddy-ratelimit \
    --with github.com/hslatman/caddy-crowdsec-bouncer/http

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
