"""
Pytest configuration file.

This file sets up the Python path so that tests can import modules
from the project root (database, src, etc.) without needing PYTHONPATH.
"""
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
