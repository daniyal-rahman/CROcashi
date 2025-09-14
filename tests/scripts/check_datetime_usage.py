#!/usr/bin/env python3
"""
Pre-commit hook to check for proper datetime usage.

This script checks that all datetime.now() calls use timezone.utc
and that datetime objects are timezone-aware.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


def check_file(file_path: Path) -> List[Tuple[int, str, str]]:
    """
    Check a single file for datetime usage issues.
    
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
        # Check for naive datetime.now() usage
        if re.search(r'datetime\.now\(\)', line):
            issues.append((
                line_num,
                line.strip(),
                "Use datetime.now(timezone.utc) instead of datetime.now()"
            ))
        
        # Check for datetime.utcnow() usage (deprecated)
        if re.search(r'datetime\.utcnow\(\)', line):
            issues.append((
                line_num,
                line.strip(),
                "Use datetime.now(timezone.utc) instead of datetime.utcnow()"
            ))
        
        # Check for datetime.now(datetime.UTC) usage (should be timezone.utc)
        if re.search(r'datetime\.now\(datetime\.UTC\)', line):
            issues.append((
                line_num,
                line.strip(),
                "Use datetime.now(timezone.utc) instead of datetime.now(datetime.UTC)"
            ))
    
    return issues


def main():
    """Main function to run the datetime usage check."""
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
        print("DATETIME USAGE ISSUES FOUND")
        print("="*80)
        print("Please fix the above issues to ensure consistent timezone handling.")
        print("Use datetime.now(timezone.utc) for all datetime operations.")
        return 1
    
    print("✅ All datetime usage looks good!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
