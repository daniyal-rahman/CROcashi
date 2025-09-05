#!/usr/bin/env python3
"""
Development setup script for CROcashi.

This script ensures proper development environment setup:
1. Installs the package in development mode
2. Verifies imports work correctly
3. Sets up basic configuration
4. Runs basic tests
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(f"   Command: {cmd}")
        print(f"   Error: {e.stderr}")
        return False


def test_imports():
    """Test that ncfd imports work correctly."""
    print("🔄 Testing imports...")
    try:
        # Test basic imports
        import ncfd
        from ncfd.config import get_config
        from ncfd.backtest.outcomes import compute_outcome_severity, OutcomeSeverity
        print("✅ All imports working correctly")
        return True
    except ImportError as e:
        print(f"❌ Import test failed: {e}")
        print("   Make sure you've run: pip install -e .")
        return False


def main():
    """Main setup function."""
    print("🚀 CROcashi Development Setup")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not Path("pyproject.toml").exists():
        print("❌ Error: pyproject.toml not found. Run this script from the project root.")
        sys.exit(1)
    
    # Step 1: Install package in development mode
    if not run_command("pip install -e .", "Installing package in development mode"):
        print("❌ Setup failed at package installation")
        sys.exit(1)
    
    # Step 2: Test imports
    if not test_imports():
        print("❌ Setup failed at import testing")
        sys.exit(1)
    
    # Step 3: Check for environment file
    if not Path(".env").exists():
        print("⚠️  Warning: .env file not found")
        print("   Copy env.example to .env and configure your environment variables")
    else:
        print("✅ Environment file found")
    
    # Step 4: Check for database configuration
    if not run_command("python -c 'import os; print(\"DATABASE_URL:\", os.getenv(\"DATABASE_URL\", \"Not set\"))'", "Checking database configuration"):
        print("⚠️  Warning: Could not check database configuration")
    
    print("\n🎉 Development setup completed successfully!")
    print("\nNext steps:")
    print("1. Configure your .env file with database and API credentials")
    print("2. Run database migrations: alembic upgrade head")
    print("3. Run tests: python -m pytest tests/")
    print("4. Start development: python -m ncfd.api.main")


if __name__ == "__main__":
    main()
