#!/usr/bin/env python3
"""
Migration script to map existing S1-S9 signals to Pattern Families (F1-F9).

This script:
1. Maps existing S1-S9 signals to appropriate F1-F9 pattern families
2. Converts severity H/M/L to 0-3 scale
3. Preserves existing data while adding new pattern family fields
4. Creates initial pattern detections from existing signals
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
from typing import Dict, List, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# S1-S9 to F1-F9 Pattern Family Mapping
SIGNAL_TO_PATTERN_MAPPING = {
    'S1': ('F3', 'F3P4', 'Endpoint/Objective Reframe'),  # Endpoint changed
    'S2': ('F2', 'F2P1', 'Underpowered vs stated effect'),  # Underpowered pivotal
    'S3': ('F1', 'F1P4', 'Multiplicity/Hierarchy Ambiguity'),  # Subgroup-only win without multiplicity
    'S4': ('F4', 'F4P3', 'Missing Data/Rescue Use Risk'),  # ITT/PP dropout asymmetry
    'S5': ('F5', 'F5P1', 'Class/Target Precedent Failures'),  # Implausible vs graveyard
    'S6': ('F2', 'F2P3', 'Informative Interim/Alpha Spending'),  # Many interims no spending
    'S7': ('F3', 'F3P1', 'Control/Blinding Adequacy'),  # Single-arm where RCT standard
    'S8': ('F2', 'F2P2', 'Model Misfit'),  # P-value cusp or heaping
    'S9': ('F5', 'F5P3', 'Biomarker/PD Misalignment'),  # OS/PFS contradiction
}

# Severity mapping H/M/L -> 3/2/1
SEVERITY_MAPPING = {
    'H': 3,  # Red
    'M': 2,  # Amber  
    'L': 1,  # Yellow
}

class SignalMigration:
    def __init__(self, database_url: str):
        """Initialize migration with database connection."""
        self.engine = create_engine(database_url)
        self.Session = sessionmaker(bind=self.engine)
        
    def migrate_signals(self) -> Dict[str, int]:
        """Migrate existing S1-S9 signals to Pattern Families."""
        logger.info("Starting S1-S9 to Pattern Families migration...")
        
        stats = {
            'signals_updated': 0,
            'pattern_detections_created': 0,
            'errors': 0
        }
        
        with self.Session() as session:
            try:
                # 1. Update existing signals table with new fields
                stats['signals_updated'] = self._update_existing_signals(session)
                
                # 2. Create pattern detections from existing signals
                stats['pattern_detections_created'] = self._create_pattern_detections(session)
                
                # 3. Commit all changes
                session.commit()
                logger.info("Migration completed successfully!")
                
            except Exception as e:
                session.rollback()
                logger.error(f"Migration failed: {e}")
                stats['errors'] += 1
                raise
                
        return stats
    
    def _update_existing_signals(self, session) -> int:
        """Update existing signals table with pattern family fields."""
        logger.info("Updating existing signals with pattern family fields...")
        
        updated_count = 0
        
        for s_id, (family_id, pattern_id, description) in SIGNAL_TO_PATTERN_MAPPING.items():
            # Update signals table
            result = session.execute(text("""
                UPDATE signals 
                SET 
                    family_id = :family_id,
                    pattern_id = :pattern_id,
                    confidence = 0.8,  -- Default confidence for migrated signals
                    why = :description,
                    detected_at = fired_at
                WHERE s_id = :s_id
            """), {
                'family_id': family_id,
                'pattern_id': pattern_id,
                'description': f"Migrated from {s_id}: {description}",
                's_id': s_id
            })
            
            updated_count += result.rowcount
            logger.info(f"Updated {result.rowcount} signals for {s_id} -> {family_id}/{pattern_id}")
        
        return updated_count
    
    def _create_pattern_detections(self, session) -> int:
        """Create pattern_detections records from existing signals."""
        logger.info("Creating pattern detections from existing signals...")
        
        # Get all signals with new pattern family data
        signals = session.execute(text("""
            SELECT 
                trial_id, run_id, s_id, family_id, pattern_id, 
                severity, confidence, why, fired_at
            FROM signals 
            WHERE family_id IS NOT NULL AND pattern_id IS NOT NULL
        """)).fetchall()
        
        created_count = 0
        
        for signal in signals:
            # Convert severity H/M/L to 0-3 scale
            old_severity = signal.severity
            new_severity = SEVERITY_MAPPING.get(old_severity, 1)
            
            # Create pattern detection record
            session.execute(text("""
                INSERT INTO pattern_detections (
                    trial_id, run_id, family_id, pattern_id, 
                    severity, confidence, why, detected_at
                ) VALUES (
                    :trial_id, :run_id, :family_id, :pattern_id,
                    :severity, :confidence, :why, :detected_at
                )
            """), {
                'trial_id': signal.trial_id,
                'run_id': signal.run_id,
                'family_id': signal.family_id,
                'pattern_id': signal.pattern_id,
                'severity': new_severity,
                'confidence': signal.confidence,
                'why': signal.why,
                'detected_at': signal.fired_at
            })
            
            created_count += 1
        
        logger.info(f"Created {created_count} pattern detection records")
        return created_count
    
    def create_family_aggregations(self) -> int:
        """Create family aggregations from pattern detections."""
        logger.info("Creating family aggregations...")
        
        with self.Session() as session:
            # Get all trials with pattern detections
            trials = session.execute(text("""
                SELECT DISTINCT trial_id, run_id 
                FROM pattern_detections
            """)).fetchall()
            
            created_count = 0
            
            for trial_id, run_id in trials:
                # Get pattern detections for this trial/run
                detections = session.execute(text("""
                    SELECT family_id, severity, confidence
                    FROM pattern_detections
                    WHERE trial_id = :trial_id AND run_id = :run_id
                """), {'trial_id': trial_id, 'run_id': run_id}).fetchall()
                
                # Group by family
                family_data = {}
                for detection in detections:
                    family_id = detection.family_id
                    if family_id not in family_data:
                        family_data[family_id] = []
                    family_data[family_id].append(detection)
                
                # Create aggregation for each family
                for family_id, family_detections in family_data.items():
                    # Calculate max severity
                    max_severity = max(d.severity for d in family_detections)
                    
                    # Calculate weighted count (severity weights: 0=0, 1=1, 2=2, 3=4)
                    severity_weights = {0: 0, 1: 1, 2: 2, 3: 4}
                    weighted_count = sum(severity_weights[d.severity] for d in family_detections)
                    
                    # Get top patterns (by severity, then confidence)
                    top_patterns = sorted(
                        family_detections,
                        key=lambda d: (d.severity, d.confidence),
                        reverse=True
                    )[:3]
                    
                    # Create family aggregation
                    session.execute(text("""
                        INSERT INTO family_aggregations (
                            trial_id, run_id, family_id, max_severity, 
                            weighted_count, top_patterns
                        ) VALUES (
                            :trial_id, :run_id, :family_id, :max_severity,
                            :weighted_count, :top_patterns
                        )
                    """), {
                        'trial_id': trial_id,
                        'run_id': run_id,
                        'family_id': family_id,
                        'max_severity': max_severity,
                        'weighted_count': weighted_count,
                        'top_patterns': [d.pattern_id for d in top_patterns]
                    })
                    
                    created_count += 1
            
            session.commit()
            logger.info(f"Created {created_count} family aggregation records")
            return created_count
    
    def validate_migration(self) -> Dict[str, int]:
        """Validate the migration results."""
        logger.info("Validating migration...")
        
        with self.Session() as session:
            # Check signals table
            signals_with_families = session.execute(text("""
                SELECT COUNT(*) FROM signals WHERE family_id IS NOT NULL
            """)).scalar()
            
            # Check pattern detections
            pattern_detections = session.execute(text("""
                SELECT COUNT(*) FROM pattern_detections
            """)).scalar()
            
            # Check family aggregations
            family_aggregations = session.execute(text("""
                SELECT COUNT(*) FROM family_aggregations
            """)).scalar()
            
            # Check pattern families configuration
            pattern_families = session.execute(text("""
                SELECT COUNT(*) FROM pattern_families
            """)).scalar()
            
            pattern_primitives = session.execute(text("""
                SELECT COUNT(*) FROM pattern_primitives
            """)).scalar()
            
            validation_results = {
                'signals_with_families': signals_with_families,
                'pattern_detections': pattern_detections,
                'family_aggregations': family_aggregations,
                'pattern_families': pattern_families,
                'pattern_primitives': pattern_primitives
            }
            
            logger.info("Validation results:")
            for key, value in validation_results.items():
                logger.info(f"  {key}: {value}")
            
            return validation_results

def main():
    """Main migration function."""
    # Get database URL from environment or use default
    database_url = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/crocashi')
    
    try:
        migration = SignalMigration(database_url)
        
        # Run migration
        stats = migration.migrate_signals()
        
        # Create family aggregations
        aggregation_stats = migration.create_family_aggregations()
        
        # Validate results
        validation = migration.validate_migration()
        
        # Print summary
        print("\n" + "="*50)
        print("MIGRATION SUMMARY")
        print("="*50)
        print(f"Signals updated: {stats['signals_updated']}")
        print(f"Pattern detections created: {stats['pattern_detections_created']}")
        print(f"Family aggregations created: {aggregation_stats}")
        print(f"Errors: {stats['errors']}")
        print("\nValidation:")
        for key, value in validation.items():
            print(f"  {key}: {value}")
        print("="*50)
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
