"""Entry point para `python -m src.modules.scoring`."""

from __future__ import annotations

import asyncio
import sys

from src.modules.scoring.cli import main

if __name__ == "__main__":
    asyncio.run(main(sys.argv))
