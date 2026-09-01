#!/bin/sh
# Make sure the persisted central-API credentials file exists, then hand over to
# the image's own startup script.
#
# This wrapper exists for one narrow reason. crowdsec/config.yaml.local points the
# central-API credentials at /etc/crowdsec/creds/, which is a volume, so that
# enrolment survives a deploy. On a fresh volume that file is absent, and then
# *every* cscli invocation fails with
#
#     failed to load Local API: loading online client credentials:
#     open /etc/crowdsec/creds/online_api_credentials.yaml: no such file or directory
#
# and startup never completes. An empty file is enough to avoid that: note the
# upstream image ships a zero-byte online_api_credentials.yaml at the default
# path for precisely this reason.
#
# What this wrapper deliberately does NOT do is register with the central API,
# even though that would be convenient. At this point in startup
# /etc/crowdsec/config.yaml does not exist yet -- the image keeps its
# configuration in /staging and docker_start.sh copies it in a moment from now --
# so cscli cannot run at all here. Registration is therefore a separate, one-time
# step: `just crowdsec-register`. See "Phase 5b" in docs/perf/crowdsec-plan.md.
set -eu

CREDS=/etc/crowdsec/creds/online_api_credentials.yaml

mkdir -p /etc/crowdsec/creds

if [ ! -e "$CREDS" ]; then
    : > "$CREDS"
    chmod 600 "$CREDS"
    echo "entrypoint: created an empty $CREDS; run 'just crowdsec-register' to enrol"
fi

# The image's own entrypoint is ["/bin/bash", "/docker_start.sh"], so invoke it
# the same way rather than relying on a shebang.
exec /bin/bash /docker_start.sh "$@"
