#!/usr/bin/env python3
"""
Pre-commit hook to check for debug print statements.

This script checks that print() statements are not used for debugging
in production code. Use proper logging instead.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


def check_file(file_path: Path) -> List[Tuple[int, str, str]]:
    """
    Check a single file for debug print statements.
    
    Returns:
        List of (line_number, line_content, issue_description) tuples
    """
    issues = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return issues
    
    for line_num, line in enumerate(lines, 1):
        # Check for print statements (excluding shebang and docstrings)
        if re.search(r'^\s*print\s*\(', line):
            # Skip if it's a shebang or in a docstring
            if not line.strip().startswith('#!') and not line.strip().startswith('"""'):
                issues.append((
                    line_num,
                    line.strip(),
                    "Use logging instead of print() for debug output"
                ))
        
        # Check for pprint usage
        if re.search(r'^\s*pprint\s*\(', line):
            issues.append((
                line_num,
                line.strip(),
                "Use logging instead of pprint() for debug output"
            ))
    
    return issues


def main():
    """Main function to run the debug print check."""
    issues_found = False
    
    # Get all Python files in src/
    src_dir = Path("src")
    if not src_dir.exists():
        print("src/ directory not found")
        return 0
    
    python_files = list(src_dir.rglob("*.py"))
    
    for file_path in python_files:
        file_issues = check_file(file_path)
        
        if file_issues:
            issues_found = True
            print(f"\n{file_path}:")
            for line_num, line_content, issue in file_issues:
                print(f"  Line {line_num}: {issue}")
                print(f"    {line_content}")
    
    if issues_found:
        print("\n" + "="*80)
        print("DEBUG PRINT STATEMENTS FOUND")
        print("="*80)
        print("Please replace print() statements with proper logging.")
        print("Use logger.debug(), logger.info(), etc. instead of print().")
        print("This ensures proper log levels and output control in production.")
        return 1
    
    print("✅ No debug print statements found!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
