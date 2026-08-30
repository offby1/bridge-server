# This image runs CrowdSec, which reads Caddy's logs and decides nothing.
#
# As of this commit there is no bouncer, so nothing this container concludes can
# block a request. It parses and counts, and that is all. See
# docs/perf/crowdsec-plan.md for what the later phases add.
#
# The acquisition config is baked into the image rather than bind-mounted, for
# exactly the reason caddy/Dockerfile bakes its Caddyfile: a bind mount resolves
# on the Docker *daemon's* filesystem, so a repo-relative path like
# ./crowdsec/acquis.d is absent when we deploy over a remote context
# (hetz-bridge, hetz-bridge-beta, mini) and the mount fails.
FROM crowdsecurity/crowdsec:v1.7.8

# One file per datasource under acquis.d/ is what upstream has recommended since
# 1.5, rather than a single acquis.yaml.
COPY acquis.d/caddy.yaml /etc/crowdsec/acquis.d/caddy.yaml

# These two files are our own parser and scenario for the rate limiter's
# rejection lines. CrowdSec loads any YAML it finds in these directories, and
# unlike the hub collections named in the compose file, these are local items
# that `cscli` reports as such.
#
# The scenario raises alerts and cannot produce a decision, because it omits the
# `remediation` label. See the scenario itself for why we consider that a better
# guarantee than simulation mode.
COPY parsers/s01-parse/caddy-ratelimit.yaml /etc/crowdsec/parsers/s01-parse/caddy-ratelimit.yaml
COPY scenarios/caddy-per-ip-ratelimit.yaml /etc/crowdsec/scenarios/caddy-per-ip-ratelimit.yaml
