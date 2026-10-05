#!/usr/bin/env python3
"""Root compatibility entry point; scripts/fastmoss_rpa.py also remains usable."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'scripts'))
from fastmoss_rpa import main
if __name__ == '__main__':
    sys.exit(main())
