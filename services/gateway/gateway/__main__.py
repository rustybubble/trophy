"""python -m gateway: serve on 127.0.0.1:(8000 + PORT_OFFSET); Caddy terminates TLS in front (/api/*)."""

import logging

import uvicorn

from .app import create_app
from .config import Settings

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    s = Settings.from_env()
    uvicorn.run(create_app(s), host="127.0.0.1", port=s.port, log_level="warning", ws_max_size=4 * 1024 * 1024)
