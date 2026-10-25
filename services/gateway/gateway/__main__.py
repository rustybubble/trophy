"""python -m gateway: serve on 127.0.0.1:(8000 + PORT_OFFSET); Caddy terminates TLS in front (/api/*).
GATEWAY_HOST=0.0.0.0 in a container, where Caddy reaches it over the compose network (D-30)."""

import logging
import os

import uvicorn

from .app import create_app
from .config import Settings

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    s = Settings.from_env()
    uvicorn.run(
        create_app(s),
        host=os.environ.get("GATEWAY_HOST", "127.0.0.1"),
        port=s.port,
        log_level="warning",
        ws_max_size=4 * 1024 * 1024,
    )
