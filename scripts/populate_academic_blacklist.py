#!/usr/bin/env python3
"""
Populate academic_blacklist table with more precise patterns.

This replaces the overly broad academic keyword detection with specific regex patterns
that are less likely to catch legitimate pharmaceutical companies.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def populate_academic_blacklist():
    """Populate academic_blacklist with precise patterns."""
    
    # Get database URL
    database_url = os.environ.get('DATABASE_URL', 'postgresql://ncfd:ncfd@localhost:5433/ncfd')
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    
    # Academic patterns (more precise than current keyword matching)
    academic_patterns = [
        # Universities and colleges
        (r'\buniversity\b', 'University/college institution'),
        (r'\bcollege\b', 'College institution'),
        (r'\bschool of medicine\b', 'Medical school'),
        (r'\bmedical school\b', 'Medical school'),
        
        # Hospitals and medical centers
        (r'\bhospital\b', 'Hospital institution'),
        (r'\bmedical center\b', 'Medical center'),
        (r'\bhealth center\b', 'Health center'),
        (r'\bclinic\b', 'Clinic'),
        
        # Research institutes
        (r'\binstitute\b', 'Research institute'),
        (r'\bfoundation\b', 'Foundation'),
        (r'\bresearch institute\b', 'Research institute'),
        
        # Government/Public health
        (r'\bnhs\b', 'National Health Service'),
        (r'\btrust\b', 'NHS Trust'),
        (r'\bpublic health\b', 'Public health agency'),
        (r'\bministry of health\b', 'Ministry of health'),
        
        # Specific academic institutions
        (r'\bmayo clinic\b', 'Mayo Clinic'),
        (r'\bcleveland clinic\b', 'Cleveland Clinic'),
        (r'\bjohns hopkins\b', 'Johns Hopkins'),
        (r'\bharvard\b', 'Harvard University'),
        (r'\bstanford\b', 'Stanford University'),
        (r'\byale\b', 'Yale University'),
        (r'\bmit\b', 'MIT'),
        (r'\bcaltech\b', 'Caltech'),
    ]
    
    with Session() as session:
        try:
            # Clear existing patterns
            session.execute(text("DELETE FROM academic_blacklist"))
            
            # Insert new patterns
            for pattern, reason in academic_patterns:
                session.execute(text("""
                    INSERT INTO academic_blacklist (pattern, reason, enabled)
                    VALUES (:pattern, :reason, true)
                """), {"pattern": pattern, "reason": reason})
            
            session.commit()
            print(f"✅ Inserted {len(academic_patterns)} academic blacklist patterns")
            
            # Show what was inserted
            result = session.execute(text("SELECT pattern, reason FROM academic_blacklist ORDER BY id"))
            print("\n📋 Academic blacklist patterns:")
            for row in result:
                print(f"  {row[0]:<30} - {row[1]}")
                
        except Exception as e:
            session.rollback()
            print(f"❌ Error populating academic blacklist: {e}")
            raise


if __name__ == "__main__":
    populate_academic_blacklist()
