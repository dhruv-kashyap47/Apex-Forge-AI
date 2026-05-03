"""
ApexForge AI — Application Entry Point
Loads environment, bootstraps the database (or demo store),
then delegates to the unified frontend.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)

from ui.frontend import main

if __name__ == "__main__":
    main()
