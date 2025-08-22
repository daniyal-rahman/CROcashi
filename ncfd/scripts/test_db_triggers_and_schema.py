#!/usr/bin/env python3
"""
Test script to verify database triggers and schema fixes.

This script tests:
1. Safe JSONB access in triggers (no crashes on null paths)
2. Robust integer parsing for sample sizes
3. Staging_errors table functionality
4. p_value generated column
5. Proper error logging instead of hard failures
"""

import psycopg2
import json
import sys
from datetime import datetime

def connect_db():
    """Connect to the database."""
    try:
        conn = psycopg2.connect(
            dbname="ncfd",
            user="postgres",
            password="postgres",
            host="localhost",
            port="5432"
        )
        return conn
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        sys.exit(1)

def test_staging_errors_table(conn):
    """Test that staging_errors table exists and has correct structure."""
    print("Testing staging_errors table...")
    
    with conn.cursor() as cur:
        # Check if table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'staging_errors'
            );
        """)
        exists = cur.fetchone()[0]
        
        if not exists:
            print("❌ staging_errors table does not exist")
            return False
        
        # Check table structure
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'staging_errors'
            ORDER BY ordinal_position;
        """)
        columns = cur.fetchall()
        
        expected_columns = [
            ('id', 'bigint', 'NO'),
            ('trial_id', 'bigint', 'YES'),
            ('study_id', 'bigint', 'YES'),
            ('error_type', 'text', 'NO'),
            ('error_message', 'text', 'NO'),
            ('extracted_jsonb', 'jsonb', 'YES'),
            ('created_at', 'timestamp with time zone', 'NO')
        ]
        
        if len(columns) != len(expected_columns):
            print(f"❌ Expected {len(expected_columns)} columns, got {len(columns)}")
            return False
        
        for i, (col_name, data_type, nullable) in enumerate(expected_columns):
            if i >= len(columns):
                print(f"❌ Missing column {col_name}")
                return False
            
            actual_name, actual_type, actual_nullable = columns[i]
            if actual_name != col_name:
                print(f"❌ Column {i}: expected {col_name}, got {actual_name}")
                return False
            
            if actual_nullable != nullable:
                print(f"❌ Column {col_name}: expected nullable={nullable}, got {actual_nullable}")
                return False
        
        # Check indexes
        cur.execute("""
            SELECT indexname FROM pg_indexes 
            WHERE tablename = 'staging_errors';
        """)
        indexes = [row[0] for row in cur.fetchall()]
        
        expected_indexes = [
            'ix_staging_errors_created_at',
            'ix_staging_errors_trial_id', 
            'ix_staging_errors_error_type'
        ]
        
        for expected_idx in expected_indexes:
            if expected_idx not in indexes:
                print(f"❌ Missing index: {expected_idx}")
                return False
        
        print("✅ staging_errors table structure is correct")
        return True

def test_p_value_generated_column(conn):
    """Test that p_value generated column exists and works."""
    print("Testing p_value generated column...")
    
    with conn.cursor() as cur:
        # Check if column exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'studies' AND column_name = 'p_value'
            );
        """)
        exists = cur.fetchone()[0]
        
        if not exists:
            print("❌ p_value column does not exist")
            return False
        
        # Check if it's a generated column
        cur.execute("""
            SELECT is_generated, generation_expression
            FROM information_schema.columns 
            WHERE table_name = 'studies' AND column_name = 'p_value';
        """)
        result = cur.fetchone()
        
        if not result or not result[0]:
            print("❌ p_value is not a generated column")
            return False
        
        print("✅ p_value generated column exists")
        
        # Check if index exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM pg_indexes 
                WHERE tablename = 'studies' AND indexname = 'ix_studies_p_value'
            );
        """)
        index_exists = cur.fetchone()[0]
        
        if not index_exists:
            print("❌ p_value index does not exist")
            return False
        
        print("✅ p_value index exists")
        return True

def test_trigger_function(conn):
    """Test that the trigger function exists and has safe JSONB access."""
    print("Testing trigger function...")
    
    with conn.cursor() as cur:
        # Check if function exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM pg_proc 
                WHERE proname = 'enforce_pivotal_study_card'
            );
        """)
        exists = cur.fetchone()[0]
        
        if not exists:
            print("❌ enforce_pivotal_study_card function does not exist")
            return False
        
        # Check function definition for safe JSONB access
        cur.execute("""
            SELECT pg_get_functiondef(oid) 
            FROM pg_proc 
            WHERE proname = 'enforce_pivotal_study_card';
        """)
        function_def = cur.fetchone()[0]
        
        # Check for safe patterns
        safe_patterns = [
            'jsonb_typeof(',
            'COALESCE(',
            'regexp_replace(',
            'RAISE WARNING',
            'staging_errors'
        ]
        
        for pattern in safe_patterns:
            if pattern not in function_def:
                print(f"❌ Missing safe pattern: {pattern}")
                return False
        
        # Check that it doesn't have dangerous patterns
        dangerous_patterns = [
            'RAISE EXCEPTION',
            'NEW.extracted_json[^b]'  # Should not reference extracted_json without 'b'
        ]
        
        for pattern in dangerous_patterns:
            if pattern in function_def:
                print(f"❌ Found dangerous pattern: {pattern}")
                return False
        
        print("✅ Trigger function has safe JSONB access")
        return True

def test_trigger_behavior(conn):
    """Test that the trigger behaves correctly with malformed data."""
    print("Testing trigger behavior...")
    
    with conn.cursor() as cur:
        # Create a test trial
        cur.execute("""
            INSERT INTO trials (trial_id, nct_id, sponsor_text, phase, indication, is_pivotal, status)
            VALUES (9999, 'NCTTEST', 'Test Sponsor', '3', 'Test Indication', true, 'completed')
            ON CONFLICT (trial_id) DO NOTHING;
        """)
        
        # Test 1: Insert with malformed JSONB (should log warning, not crash)
        try:
            cur.execute("""
                INSERT INTO studies (study_id, trial_id, doc_type, citation, year, url, oa_status, extracted_jsonb)
                VALUES (9999, 9999, 'Paper', 'Test Citation', 2024, 'http://test.com', 'unknown', 
                        '{"sample_size": {"total_n": "invalid_number"}, "results": {"primary": [{}]}}'::jsonb);
            """)
            
            # Check if error was logged to staging_errors
            cur.execute("""
                SELECT COUNT(*) FROM staging_errors 
                WHERE trial_id = 9999 AND error_type = 'pivotal_validation';
            """)
            error_count = cur.fetchone()[0]
            
            if error_count > 0:
                print("✅ Trigger correctly logged validation error to staging_errors")
            else:
                print("❌ Trigger did not log validation error")
                return False
                
        except Exception as e:
            print(f"❌ Trigger crashed with error: {e}")
            return False
        
        # Test 2: Insert with valid JSONB (should succeed)
        try:
            cur.execute("""
                INSERT INTO studies (study_id, trial_id, doc_type, citation, year, url, oa_status, extracted_jsonb)
                VALUES (9998, 9999, 'Paper', 'Valid Citation', 2024, 'http://valid.com', 'unknown',
                        '{"primary_endpoints": ["endpoint1"], "sample_size": {"total_n": 100}, 
                          "populations": {"analysis_primary_on": "ITT"}, 
                          "results": {"primary": [{"p_value": 0.05}]}}'::jsonb);
            """)
            print("✅ Trigger correctly allowed valid data")
            
        except Exception as e:
            print(f"❌ Trigger incorrectly blocked valid data: {e}")
            return False
        
        # Test 3: Check p_value generated column
        cur.execute("""
            SELECT p_value FROM studies WHERE study_id = 9998;
        """)
        p_value = cur.fetchone()[0]
        
        if p_value == 0.05:
            print("✅ p_value generated column works correctly")
        else:
            print(f"❌ p_value generated column failed: expected 0.05, got {p_value}")
            return False
        
        # Cleanup
        cur.execute("DELETE FROM studies WHERE study_id IN (9999, 9998);")
        cur.execute("DELETE FROM trials WHERE trial_id = 9999;")
        cur.execute("DELETE FROM staging_errors WHERE trial_id = 9999;")
        
        return True

def main():
    """Run all tests."""
    print("🧪 Testing Database Triggers and Schema Fixes")
    print("=" * 50)
    
    conn = connect_db()
    
    tests = [
        test_staging_errors_table,
        test_p_value_generated_column,
        test_trigger_function,
        test_trigger_behavior
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test(conn):
                passed += 1
            print()
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            print()
    
    conn.close()
    
    print("=" * 50)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Database triggers and schema are working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the database setup.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
