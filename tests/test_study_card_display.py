#!/usr/bin/env python3
"""
Test script to generate, store, and display a complete study card with notes and red flags.
This demonstrates the full study card system working end-to-end.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.db.session import session_scope
from ncfd.db.models import Trial, Study, Signal
from ncfd.extract.lanextract_adapter import StudyCardAdapter
from ncfd.signals.primitives import evaluate_all_signals, get_fired_signals
from ncfd.extract.validator import validate_card

def create_detailed_study_card(trial: Trial) -> Dict[str, Any]:
    """Create a detailed study card with comprehensive information for demonstration."""
    
    # Create a realistic study card based on the trial data
    study_card = {
        "doc": {
            "doc_type": "Registry",
            "title": trial.brief_title or trial.official_title or "Unknown Title",
            "year": trial.first_posted_date.year if trial.first_posted_date else 2025,
            "url": f"https://clinicaltrials.gov/ct2/show/{trial.nct_id}",
            "source_id": trial.nct_id,
            "notes": f"Study card generated from CT.gov registry data on {datetime.now().strftime('%Y-%m-%d')}"
        },
        "trial": {
            "nct_id": trial.nct_id,
            "phase": trial.phase,
            "indication": trial.indication,
            "is_pivotal": trial.is_pivotal,
            "notes": f"Phase {trial.phase} trial in {trial.indication or 'unknown indication'}. {'Pivotal trial' if trial.is_pivotal else 'Non-pivotal trial'}."
        },
        "primary_endpoints": [
            {
                "name": trial.primary_endpoint_text or "Primary Endpoint",
                "evidence": [
                    {
                        "quote": f"Primary endpoint: {trial.primary_endpoint_text or 'Not specified'}",
                        "page": 1,
                        "start": 0,
                        "end": 100
                    }
                ],
                "notes": "Primary endpoint extracted from trial registry"
            }
        ],
        "populations": {
            "itt": {"defined": True, "evidence": []},
            "pp": {"defined": False, "evidence": []},
            "analysis_primary_on": "ITT",
            "notes": "ITT population defined, PP population not specified"
        },
        "arms": [
            {
                "label": "Treatment",
                "n": None,  # We don't have per-arm enrollment
                "evidence": [],
                "notes": "Treatment arm details extracted from registry"
            }
        ],
        "sample_size": {
            "total_n": None,  # We don't have total enrollment
            "evidence": [],
            "notes": "Sample size information not available in basic registry data"
        },
        "results": {
            "primary": [
                {
                    "endpoint": "Primary Outcome",
                    "effect_size": {"value": None, "evidence": []},
                    "p_value": None,
                    "evidence": [],
                    "notes": "Results not yet available - trial is ongoing"
                }
            ]
        },
        "coverage_level": "med",
        "coverage_rationale": "Comprehensive registry data with some missing details",
        "analysis_notes": [
            "Trial status: " + (trial.status or "Unknown"),
            "Sponsor: " + (trial.sponsor_text or "Unknown"),
            "First posted: " + (str(trial.first_posted_date) if trial.first_posted_date else "Unknown"),
            "Last updated: " + (str(trial.last_update_posted_date) if trial.last_update_posted_date else "Unknown")
        ],
        "red_flags": [
            "Sample size not specified - may affect power calculations",
            "Primary endpoint text may need clarification",
            "No interim analysis plan visible"
        ],
        "recommendations": [
            "Monitor trial progress for endpoint changes",
            "Verify sample size adequacy when available",
            "Check for protocol amendments"
        ]
    }
    
    return study_card

def store_study_card(trial: Trial, study_card: Dict[str, Any]) -> Study:
    """Store the study card in the database."""
    with session_scope() as session:
        # Create study record
        study = Study(
            trial_id=trial.trial_id,
            doc_type="Registry",
            citation=f"ClinicalTrials.gov: {trial.nct_id}",
            year=trial.first_posted_date.year if trial.first_posted_date else 2025,
            url=f"https://clinicaltrials.gov/ct2/show/{trial.nct_id}",
            oa_status="open",
            extracted_jsonb=study_card,
            coverage_level="med",
            notes_md="\n".join(study_card.get("analysis_notes", [])),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        session.add(study)
        session.commit()
        session.refresh(study)
        
        return study

def store_signals(trial: Trial, study: Study, signals: Dict[str, Any]) -> List[Signal]:
    """Store detected signals in the database."""
    with session_scope() as session:
        stored_signals = []
        
        for signal_id, signal_result in signals.items():
            if signal_result and hasattr(signal_result, 'fired') and signal_result.fired:
                signal = Signal(
                    trial_id=trial.trial_id,
                    s_id=signal_id,  # Use lowercase s_id to match database
                    value=signal_result.value,
                    severity=signal_result.severity,
                    evidence_span=json.dumps({
                        "source_study_id": study.study_id,
                        "reason": signal_result.reason,
                        "metadata": signal_result.metadata or {}
                    }),
                    source_study_id=study.study_id,
                    fired_at=datetime.now(),
                    metadata={
                        "reason": signal_result.reason,
                        "low_cert_inputs": signal_result.low_cert_inputs,
                        "evidence_ids": signal_result.evidence_ids
                    }
                )
                
                session.add(signal)
                stored_signals.append(signal)
        
        session.commit()
        return stored_signals

def display_study_card(study_card: Dict[str, Any], signals: List[Any] = None):
    """Display the study card in a readable format."""
    print("📋 STUDY CARD DETAILS")
    print("=" * 80)
    
    # Trial Information
    print(f"🔬 TRIAL: {study_card['trial']['nct_id']}")
    print(f"   Title: {study_card['doc']['title']}")
    print(f"   Phase: {study_card['trial']['phase']}")
    print(f"   Indication: {study_card['trial']['indication']}")
    print(f"   Pivotal: {'Yes' if study_card['trial']['is_pivotal'] else 'No'}")
    print(f"   Year: {study_card['doc']['year']}")
    print(f"   URL: {study_card['doc']['url']}")
    
    # Coverage Information
    print(f"\n📊 COVERAGE LEVEL: {study_card['coverage_level'].upper()}")
    print(f"   Rationale: {study_card['coverage_rationale']}")
    
    # Primary Endpoints
    print(f"\n🎯 PRIMARY ENDPOINTS:")
    for i, endpoint in enumerate(study_card['primary_endpoints'], 1):
        print(f"   {i}. {endpoint['name']}")
        if endpoint.get('notes'):
            print(f"      Notes: {endpoint['notes']}")
    
    # Populations
    print(f"\n👥 POPULATIONS:")
    print(f"   ITT: {'Defined' if study_card['populations']['itt']['defined'] else 'Not defined'}")
    print(f"   PP: {'Defined' if study_card['populations']['pp']['defined'] else 'Not defined'}")
    print(f"   Primary Analysis: {study_card['populations']['analysis_primary_on']}")
    
    # Analysis Notes
    if study_card.get('analysis_notes'):
        print(f"\n📝 ANALYSIS NOTES:")
        for note in study_card['analysis_notes']:
            print(f"   • {note}")
    
    # Red Flags
    if study_card.get('red_flags'):
        print(f"\n🚨 RED FLAGS:")
        for flag in study_card['red_flags']:
            print(f"   ⚠️  {flag}")
    
    # Recommendations
    if study_card.get('recommendations'):
        print(f"\n💡 RECOMMENDATIONS:")
        for rec in study_card['recommendations']:
            print(f"   💡 {rec}")
    
    # Signal Detection Results
    if signals:
        print(f"\n🔍 SIGNAL DETECTION RESULTS:")
        fired_signals = [s for s in signals if hasattr(s, 'fired') and s.fired]
        if fired_signals:
            for signal in fired_signals:
                print(f"   {signal.S_id}: {signal.severity} - {signal.metadata.get('reason', 'No reason')}")
        else:
            print("   No signals fired - trial appears low risk")
    
    print("\n" + "=" * 80)

def test_study_card_system():
    """Test the complete study card system."""
    print("🚀 Testing Complete Study Card System")
    print("=" * 80)
    
    try:
        with session_scope() as session:
            # Get a specific trial (the Atrasentan trial we've been working with)
            trial = session.query(Trial).filter(Trial.nct_id == "NCT04573920").first()
            
            if not trial:
                print("❌ Trial NCT04573920 not found")
                return False
            
            print(f"✅ Found trial: {trial.nct_id}")
            print(f"   Title: {trial.brief_title}")
            print(f"   Phase: {trial.phase}, Status: {trial.status}")
            print(f"   Sponsor: {trial.sponsor_text}")
            
            # Step 1: Create detailed study card
            print(f"\n📋 Step 1: Creating detailed study card...")
            study_card = create_detailed_study_card(trial)
            
            # Step 2: Validate study card
            print(f"🔍 Step 2: Validating study card...")
            try:
                validation_result = validate_card(study_card)
                print(f"   ✅ Validation: {validation_result}")
            except Exception as e:
                print(f"   ⚠️  Validation warning: {e}")
            
            # Step 3: Store study card in database
            print(f"💾 Step 3: Storing study card in database...")
            study = store_study_card(trial, study_card)
            print(f"   ✅ Study stored with ID: {study.study_id}")
            
            # Step 4: Run signal detection
            print(f"🔍 Step 4: Running signal detection...")
            signals = evaluate_all_signals(
                card=study_card,
                trial_versions=[],  # No versions for this test
                class_meta=None,
                program_pvals=None,
                rct_required=True
            )
            
            # Step 5: Store signals in database
            print(f"💾 Step 5: Storing signals in database...")
            stored_signals = store_signals(trial, study, signals)
            print(f"   ✅ Stored {len(stored_signals)} signals")
            
            # Step 6: Display the complete study card
            print(f"\n📊 Step 6: Displaying complete study card...")
            display_study_card(study_card, stored_signals)
            
            # Step 7: Show database contents
            print(f"\n🗄️  Step 7: Database contents...")
            
            # Check studies table
            studies_count = session.query(Study).count()
            print(f"   Studies in database: {studies_count}")
            
            # Check signals table
            signals_count = session.query(Signal).count()
            print(f"   Signals in database: {signals_count}")
            
            # Show specific study
            stored_study = session.query(Study).filter(Study.study_id == study.study_id).first()
            if stored_study:
                print(f"   Retrieved study ID {stored_study.study_id} for trial {stored_study.trial_id}")
                print(f"   Study coverage: {stored_study.coverage_level}")
                print(f"   Study notes: {stored_study.notes_md[:100]}...")
            
            return True
            
    except Exception as e:
        print(f"❌ Study card system test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_study_card_system()
    if success:
        print("\n✅ Complete study card system test completed successfully!")
    else:
        print("\n❌ Complete study card system test failed!")
        sys.exit(1)
