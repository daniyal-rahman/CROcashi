#!/usr/bin/env python3
"""
Pre-commit hook to check for MD5 usage.

This script checks that MD5 is not used for security purposes,
as it's cryptographically broken.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


def check_file(file_path: Path) -> List[Tuple[int, str, str]]:
    """
    Check a single file for MD5 usage issues.
    
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
        # Check for MD5 usage
        if re.search(r'hashlib\.md5', line):
            issues.append((
                line_num,
                line.strip(),
                "MD5 is cryptographically broken. Use hashlib.sha256 instead"
            ))
        
        # Check for direct MD5 imports
        if re.search(r'from.*md5|import.*md5', line):
            issues.append((
                line_num,
                line.strip(),
                "MD5 is cryptographically broken. Use hashlib.sha256 instead"
            ))
    
    return issues


def main():
    """Main function to run the MD5 usage check."""
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
        print("MD5 USAGE ISSUES FOUND")
        print("="*80)
        print("Please replace MD5 with SHA-256 for security purposes.")
        print("MD5 is cryptographically broken and vulnerable to collisions.")
        print("Use hashlib.sha256() instead of hashlib.md5().")
        return 1
    
    print("✅ No MD5 usage found!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
