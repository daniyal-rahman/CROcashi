#!/usr/bin/env python3
"""
Data Integrity Validation Script

This script validates data integrity before applying foreign key constraints.
Run this before applying migrations to ensure no orphaned records exist.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import create_engine, text
from ncfd.db.models import Base
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_data_integrity():
    """Validate data integrity for foreign key constraints."""
    
    # Database URL (update as needed)
    DATABASE_URL = "postgresql://user:password@localhost:5433/ncfd"
    
    try:
        engine = create_engine(DATABASE_URL)
        
        with engine.connect() as conn:
            logger.info("Starting data integrity validation...")
            
            # Check for orphaned study_cards.doc_id references
            result = conn.execute(text("""
                SELECT COUNT(*) as orphaned_count
                FROM study_cards sc
                LEFT JOIN documents d ON sc.doc_id = d.doc_id
                WHERE d.doc_id IS NULL
            """))
            orphaned_study_cards = result.fetchone()[0]
            
            if orphaned_study_cards > 0:
                logger.error(f"❌ Found {orphaned_study_cards} orphaned study_cards.doc_id references")
                return False
            else:
                logger.info("✅ No orphaned study_cards.doc_id references found")
            
            # Check for orphaned factsheets.doc_id references
            result = conn.execute(text("""
                SELECT COUNT(*) as orphaned_count
                FROM factsheets f
                LEFT JOIN documents d ON f.doc_id = d.doc_id
                WHERE d.doc_id IS NULL
            """))
            orphaned_factsheets = result.fetchone()[0]
            
            if orphaned_factsheets > 0:
                logger.error(f"❌ Found {orphaned_factsheets} orphaned factsheets.doc_id references")
                return False
            else:
                logger.info("✅ No orphaned factsheets.doc_id references found")
            
            # Check for orphaned company_aliases.company_id references
            result = conn.execute(text("""
                SELECT COUNT(*) as orphaned_count
                FROM company_aliases ca
                LEFT JOIN companies c ON ca.company_id = c.company_id
                WHERE c.company_id IS NULL
            """))
            orphaned_aliases = result.fetchone()[0]
            
            if orphaned_aliases > 0:
                logger.error(f"❌ Found {orphaned_aliases} orphaned company_aliases.company_id references")
                return False
            else:
                logger.info("✅ No orphaned company_aliases.company_id references found")
            
            # Check for duplicate doc_id values in study_cards
            result = conn.execute(text("""
                SELECT doc_id, COUNT(*) as count
                FROM study_cards
                GROUP BY doc_id
                HAVING COUNT(*) > 1
            """))
            duplicates = result.fetchall()
            
            if duplicates:
                logger.error(f"❌ Found duplicate doc_id values in study_cards: {duplicates}")
                return False
            else:
                logger.info("✅ No duplicate doc_id values in study_cards")
            
            # Check for duplicate doc_id values in factsheets
            result = conn.execute(text("""
                SELECT doc_id, COUNT(*) as count
                FROM factsheets
                GROUP BY doc_id
                HAVING COUNT(*) > 1
            """))
            duplicates = result.fetchall()
            
            if duplicates:
                logger.error(f"❌ Found duplicate doc_id values in factsheets: {duplicates}")
                return False
            else:
                logger.info("✅ No duplicate doc_id values in factsheets")
            
            logger.info("🎉 All data integrity checks passed!")
            return True
            
    except Exception as e:
        logger.error(f"❌ Data integrity validation failed: {e}")
        return False

if __name__ == "__main__":
    success = validate_data_integrity()
    sys.exit(0 if success else 1)
