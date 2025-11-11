"""
Test script for priority failure signal sources.

Tests:
1. FDA Clinical Hold
2. FDA Warning Letters
3. California WARN
4. Federal WARN
5. FDA Breakthrough (success benchmark)
"""
import sys
from database.config import get_db_session
from src.processing.pipeline import ProcessingPipeline
from sqlalchemy import text

def check_staging_data(source_name: str):
    """Check how many records are in staging for a source."""
    with get_db_session() as session:
        query = text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE processed = false) as unprocessed,
                COUNT(*) FILTER (WHERE processed = true) as processed
            FROM staging_raw_data
            WHERE source_system = :source_name
        """)
        result = session.execute(query, {'source_name': source_name}).fetchone()
        return {
            'total': result[0] if result else 0,
            'unprocessed': result[1] if result else 0,
            'processed': result[2] if result else 0
        }

def test_source(source_name: str, limit: int = 10):
    """Test processing a source."""
    print(f"\n{'='*60}")
    print(f"TESTING: {source_name.upper()}")
    print(f"{'='*60}")
    
    # Check staging data
    staging = check_staging_data(source_name)
    print(f"\n📊 Staging Data:")
    print(f"   - Total records: {staging['total']}")
    print(f"   - Unprocessed: {staging['unprocessed']}")
    print(f"   - Already processed: {staging['processed']}")
    
    if staging['total'] == 0:
        print(f"\n⚠️  No data in staging for {source_name}")
        print(f"   Need to run ingestion first")
        return None
    
    # Process source
    print(f"\n🔄 Processing {min(limit, staging['unprocessed'])} records...")
    pipeline = ProcessingPipeline(batch_size=10)
    
    try:
        stats = pipeline.process_source(source_name, limit=limit)
        
        print(f"\n✅ Processing Results:")
        print(f"   - Records processed: {stats.get('records_processed', 0)}")
        print(f"   - Records failed: {stats.get('records_failed', 0)}")
        print(f"   - Entities created: {stats.get('entities_created', 0)}")
        print(f"   - Entities matched: {stats.get('entities_matched', 0)}")
        print(f"   - Relationships created: {stats.get('relationships_created', 0)}")
        
        return stats
        
    except Exception as e:
        print(f"\n❌ Error processing {source_name}: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_events(source_name: str):
    """Check events created by a source."""
    with get_db_session() as session:
        # Check regulatory_events table
        query_reg = text("""
            SELECT 
                event_type,
                COUNT(*) as count
            FROM regulatory_events
            WHERE data_sources->>'source' = :source_name
            AND deleted_at IS NULL
            GROUP BY event_type
            ORDER BY count DESC
        """)
        results_reg = session.execute(query_reg, {'source_name': source_name}).fetchall()
        
        # Check events table (unified event stream) - join with sources
        query_events = text("""
            SELECT 
                e.event_type,
                COUNT(*) as count
            FROM events e
            JOIN sources s ON e.source_id = s.source_id
            WHERE s.source_name = :source_name
            AND e.deleted_at IS NULL
            GROUP BY e.event_type
            ORDER BY count DESC
        """)
        results_events = session.execute(query_events, {'source_name': source_name}).fetchall()
        
        if results_reg or results_events:
            print(f"\n📊 Events Created:")
            for event_type, count in results_reg:
                print(f"   - {event_type} (regulatory_events): {count}")
            for event_type, count in results_events:
                print(f"   - {event_type} (events): {count}")
        else:
            print(f"\n⚠️  No events found for {source_name}")

def check_all_events():
    """Check all events in database."""
    with get_db_session() as session:
        # Check regulatory_events
        query_reg = text("""
            SELECT 
                event_type,
                COUNT(*) as count
            FROM regulatory_events
            WHERE deleted_at IS NULL
            GROUP BY event_type
            ORDER BY count DESC
        """)
        results_reg = session.execute(query_reg).fetchall()
        
        # Check events (unified event stream)
        query_events = text("""
            SELECT 
                event_type,
                COUNT(*) as count
            FROM events
            WHERE deleted_at IS NULL
            GROUP BY event_type
            ORDER BY count DESC
        """)
        results_events = session.execute(query_events).fetchall()
        
        print(f"\n{'='*60}")
        print("ALL EVENTS IN DATABASE")
        print(f"{'='*60}")
        
        total_reg = sum(count for _, count in results_reg)
        total_events = sum(count for _, count in results_events)
        total = total_reg + total_events
        
        if total > 0:
            print(f"\n✅ Total events: {total}")
            print(f"   - Regulatory events: {total_reg}")
            print(f"   - Unified events: {total_events}")
            print(f"\nRegulatory Event Types:")
            for event_type, count in results_reg:
                print(f"   - {event_type}: {count}")
            print(f"\nUnified Event Types:")
            for event_type, count in results_events:
                print(f"   - {event_type}: {count}")
        else:
            print("\n⚠️  No events found")

def main():
    """Test all priority failure signal sources."""
    print("\n" + "="*60)
    print("PRIORITY FAILURE SIGNAL SOURCES - TESTING")
    print("="*60)
    
    sources = [
        ('fda_clinical_hold', 20, 'CRITICAL - Direct failure indicator'),
        ('fda_warning_letters', 20, 'CRITICAL - Regulatory risk'),
        ('california_warn', 20, 'HIGH - Layoff signals'),
        ('federal_warn', 20, 'HIGH - Layoff signals'),
        ('fda_breakthrough', 20, 'HIGH - Success benchmark'),
    ]
    
    results = {}
    
    for source_name, limit, description in sources:
        print(f"\n{'='*60}")
        print(f"{source_name.upper()}: {description}")
        print(f"{'='*60}")
        
        result = test_source(source_name, limit)
        if result:
            check_events(source_name)
            results[source_name] = result
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    for source_name, result in results.items():
        if result:
            status = "✅" if result.get('records_processed', 0) > 0 else "⚠️"
            print(f"{status} {source_name}: {result.get('records_processed', 0)} processed")
    
    # Check all events
    check_all_events()
    
    # Verification queries
    print(f"\n{'='*60}")
    print("VERIFICATION QUERIES")
    print(f"{'='*60}")
    print("\nRun these queries to verify events:")
    print("""
    -- Check event types
    SELECT event_type, COUNT(*) as count
    FROM regulatory_events
    WHERE deleted_at IS NULL
    GROUP BY event_type
    ORDER BY count DESC;
    
    -- Check events in last 12 months
    SELECT COUNT(*) FROM regulatory_events 
    WHERE event_date >= CURRENT_DATE - INTERVAL '12 months'
    AND deleted_at IS NULL;
    
    -- Companies with multiple failures
    SELECT 
        c.name,
        COUNT(DISTINCT e.event_id) as failure_count,
        array_agg(DISTINCT e.event_type) as failure_types
    FROM companies c
    JOIN regulatory_company_events rce ON c.company_id = rce.company_id
    JOIN regulatory_events e ON rce.event_id = e.event_id
    WHERE e.event_date >= CURRENT_DATE - INTERVAL '12 months'
    AND e.deleted_at IS NULL
    GROUP BY c.company_id, c.name
    HAVING COUNT(DISTINCT e.event_id) >= 2
    ORDER BY failure_count DESC
    LIMIT 20;
    """)

if __name__ == '__main__':
    main()

