#!/usr/bin/env python3
"""
Runner for Cassava Extraction Focused Test
"""

import asyncio
import sys
import os

# Add the test script to path
sys.path.insert(0, os.path.dirname(__file__))

from cassava_extraction_focused_test import main

if __name__ == "__main__":
    asyncio.run(main())
