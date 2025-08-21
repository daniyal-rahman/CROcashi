#!/usr/bin/env python3
"""
Quick smoke test for Study Card JSON schema validation
"""

import json
import sys
from pathlib import Path

def test_schema_loading():
    """Test that the schema can be loaded and is valid JSON."""
    try:
        schema_path = Path("src/ncfd/extract/study_card.schema.json")
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        
        print("✅ Schema loaded successfully")
        print(f"   Title: {schema.get('title', 'N/A')}")
        print(f"   Required fields: {schema.get('required', [])}")
        print(f"   Properties count: {len(schema.get('properties', {}))}")
        
        return True
    except Exception as e:
        print(f"❌ Schema loading failed: {e}")
        return False

def test_schema_structure():
    """Test that the schema has the expected structure."""
    try:
        schema_path = Path("src/ncfd/extract/study_card.schema.json")
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        
        # Check required top-level fields
        required_fields = schema.get('required', [])
        expected_required = ['doc', 'trial', 'primary_endpoints', 'populations', 'arms', 'results', 'coverage_level']
        
        missing_required = set(expected_required) - set(required_fields)
        if missing_required:
            print(f"❌ Missing required fields: {missing_required}")
            return False
        
        # Check that $defs exist
        if '$defs' not in schema:
            print("❌ Missing $defs section")
            return False
        
        print("✅ Schema structure validation passed")
        return True
        
    except Exception as e:
        print(f"❌ Schema structure validation failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Study Card JSON Schema")
    print("=" * 40)
    
    test1 = test_schema_loading()
    test2 = test_schema_structure()
    
    if test1 and test2:
        print("\n🎉 All schema tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some schema tests failed!")
        sys.exit(1)
