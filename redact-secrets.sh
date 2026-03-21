#!/usr/bin/env bash
# Filter stdin, replacing known secret patterns with REDACTED placeholders.
# Used by dump recipes in justfile and postgres.just to prevent secrets
# from landing in committed files.
#
# Add new patterns here as needed.  Each sed expression should replace
# the secret value with a tag that makes it obvious the dump was sanitized.

exec sed \
    -e 's/GOCSPX-[a-zA-Z0-9_-]\{28,\}/REDACTED-google-oauth-client-secret/g'
