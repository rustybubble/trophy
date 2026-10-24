"""`python -m rulebook_scraper` (the Dockerfile's command)."""

import asyncio

from rulebook_scraper.main import main

asyncio.run(main())
