# One-shot admin tools for SpacetimeDB on the box: publish the Trophy module and register the service identities.
#   docker compose run --rm stdb-admin
# The CLI's owner identity lives on the stdb-cli volume, and provision.py writes the service tokens into the host's
# env file (mounted read-write only for this container).
FROM clockworklabs/spacetime:v2.13.0 AS stdb

FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=stdb /opt/spacetime /opt/spacetime
RUN ln -s /opt/spacetime/spacetimedb-cli /usr/local/bin/spacetime
WORKDIR /app
COPY spacetime spacetime
RUN cd spacetime && npm install --no-audit --no-fund --omit=dev
CMD ["sh", "/app/spacetime/scripts/box_publish.sh"]
