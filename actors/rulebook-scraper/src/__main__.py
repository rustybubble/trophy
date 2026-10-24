"""`apify run` entry point: the Apify CLI runs `python -m src` from the actor root (the Python template layout).

The package itself is `src/rulebook_scraper`; `uv sync` installs it into `.venv`, and the Dockerfile puts `src` on
`PYTHONPATH`, so this shim only forwards to it.
"""

import asyncio

from rulebook_scraper.main import main

asyncio.run(main())
