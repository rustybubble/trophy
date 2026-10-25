#!/bin/sh
# Publish the Trophy module to the compose SpacetimeDB and register engine/vision/compiler identities (D-25, D-30).
# Runs inside the stdb-admin container: `docker compose run --rm stdb-admin`. Add `--delete-data=on-conflict` via
# STDB_PUBLISH_FLAGS for a breaking schema change (it wipes game state).
set -eu
URI="${SPACETIME_URI:-http://spacetimedb:3000}"
MODULE="${SPACETIME_MODULE:-trophy}"
ENV_FILE="${TROPHY_ENV_FILE_IN_CONTAINER:-/etc/trophy/trophy.env}"
spacetime server add box --url "$URI" --no-fingerprint --default 2>/dev/null || spacetime server set-default box
# shellcheck disable=SC2086
spacetime publish -s box -p /app/spacetime --yes=skip-login,remote ${STDB_PUBLISH_FLAGS:-} "$MODULE"
python3 /app/spacetime/scripts/provision.py --env-file "$ENV_FILE"
