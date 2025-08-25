#!/usr/bin/env python3
"""
Test script for signal detection system using ingested trial data.
This tests the S1-S9 signal primitives and G1-G4 gates.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.db.session import session_scope
from ncfd.db.models import Trial, Company, TrialVersion
from ncfd.signals.primitives import evaluate_all_signals, get_fired_signals, get_high_severity_signals
from ncfd.signals.gates import evaluate_gates, get_fired_gates, calculate_total_likelihood_ratio

def test_signal_detection():
    """Test signal detection on ingested trial data."""
    print("🚀 Testing Signal Detection System")
    print("=" * 70)
    
    try:
        with session_scope() as session:
            # Get some trials to test
            trials = session.query(Trial).limit(10).all()
            
            if not trials:
                print("❌ No trials found in database")
                return False
            
            print(f"✅ Found {len(trials)} trials for signal detection testing")
            
            # Test signal detection for each trial
            signal_results = {}
            gate_results = {}
            
            for trial in trials:
                print(f"\n🔍 Analyzing trial: {trial.nct_id}")
                print(f"   Title: {trial.brief_title[:80] if trial.brief_title else 'No title'}...")
                print(f"   Phase: {trial.phase}, Status: {trial.status}")
                print(f"   Sponsor: {trial.sponsor_text or 'Unknown'}")
                
                # Create a basic study card from trial data
                study_card = create_study_card_from_trial(trial)
                
                # Get trial versions for S1 signal (endpoint changes)
                trial_versions = session.query(TrialVersion).filter(
                    TrialVersion.trial_id == trial.trial_id
                ).all()
                
                # Evaluate all signals
                try:
                    signals = evaluate_all_signals(
                        card=study_card,
                        trial_versions=trial_versions,
                        class_meta=None,  # We don't have class metadata yet
                        program_pvals=None,  # We don't have program p-values yet
                        rct_required=True
                    )
                    
                    # Get fired signals
                    fired_signals = get_fired_signals(signals)
                    high_severity = get_high_severity_signals(signals)
                    
                    print(f"   📊 Signals evaluated: {len(signals)}")
                    print(f"   ⚠️  Fired signals: {len(fired_signals)}")
                    
                    if fired_signals:
                        for signal_id, result in fired_signals.items():
                            print(f"      {signal_id}: {result.severity} - {result.reason}")
                    
                    # Store results
                    signal_results[trial.nct_id] = {
                        'signals': signals,
                        'fired_signals': fired_signals,
                        'high_severity': high_severity
                    }
                    
                except Exception as e:
                    print(f"   ❌ Signal evaluation failed: {e}")
                    signal_results[trial.nct_id] = {'error': str(e)}
                
                # Evaluate gates (G1-G4)
                try:
                    if trial.nct_id in signal_results and 'error' not in signal_results[trial.nct_id]:
                        # Create evidence_by_signal mapping for gate evaluation
                        evidence_by_signal = {}
                        present_signals = set()
                        
                        for signal_id, signal_result in signal_results[trial.nct_id]['signals'].items():
                            if signal_result and hasattr(signal_result, 'fired') and signal_result.fired:
                                present_signals.add(signal_id)
                                evidence_by_signal[signal_id] = []
                        
                        print(f"   📊 Present signals: {present_signals}")
                        
                        # Evaluate gates using the new system
                        gate_evals = evaluate_gates(
                            present_signals=present_signals,
                            evidence_by_signal=evidence_by_signal
                        )
                        
                        # Convert to legacy format for compatibility
                        fired_gates = []
                        total_lr = 1.0
                        
                        for gate_id, gate_eval in gate_evals.items():
                            if gate_eval.fired:
                                fired_gates.append({
                                    'gate_id': gate_id,
                                    'fired': True,
                                    'severity': 'H' if gate_eval.lr_used > 5.0 else 'M',
                                    'reason': gate_eval.rationale
                                })
                                total_lr *= gate_eval.lr_used
                        
                        print(f"   🚪 Gates evaluated: {len(gate_evals)}")
                        print(f"   🚨 Fired gates: {len(fired_gates)}")
                        print(f"   📈 Total likelihood ratio: {total_lr:.3f}")
                        
                        if fired_gates:
                            for gate in fired_gates:
                                print(f"      {gate['gate_id']}: {gate['severity']} - {gate['reason']}")
                        
                        gate_results[trial.nct_id] = {
                            'gates': gate_evals,
                            'fired_gates': fired_gates,
                            'total_likelihood_ratio': total_lr
                        }
                    else:
                        print(f"   ⏭️  Skipping gate evaluation due to signal errors")
                        
                except Exception as e:
                    print(f"   ❌ Gate evaluation failed: {e}")
                    gate_results[trial.nct_id] = {'error': str(e)}
            
            # Summary
            print(f"\n📋 SIGNAL DETECTION TEST SUMMARY")
            print("=" * 50)
            
            total_trials = len(trials)
            successful_signals = len([r for r in signal_results.values() if 'error' not in r])
            successful_gates = len([r for r in gate_results.values() if 'error' not in r])
            
            total_signals_fired = sum(
                len(r['fired_signals']) for r in signal_results.values() 
                if 'error' not in r
            )
            
            total_gates_fired = sum(
                len(r['fired_gates']) for r in gate_results.values() 
                if 'error' not in r
            )
            
            print(f"Trials analyzed: {total_trials}")
            print(f"Successful signal evaluation: {successful_signals}/{total_trials}")
            print(f"Successful gate evaluation: {successful_gates}/{total_trials}")
            print(f"Total signals fired: {total_signals_fired}")
            print(f"Total gates fired: {total_gates_fired}")
            
            # Show some examples of fired signals
            if total_signals_fired > 0:
                print(f"\n🔍 Examples of fired signals:")
                for trial_id, result in signal_results.items():
                    if 'error' not in result and result['fired_signals']:
                        print(f"  {trial_id}: {list(result['fired_signals'].keys())}")
            
            return True
            
    except Exception as e:
        print(f"❌ Signal detection test failed: {e}")
        return False

def create_study_card_from_trial(trial: Trial) -> Dict[str, Any]:
    """Create a basic study card from trial data for signal testing."""
    study_card = {
        "doc": {
            "doc_type": "Registry",
            "title": trial.brief_title or trial.official_title or "Unknown Title",
            "year": trial.first_posted_date.year if trial.first_posted_date else None,
            "url": f"https://clinicaltrials.gov/ct2/show/{trial.nct_id}",
            "source_id": trial.nct_id
        },
        "trial": {
            "nct_id": trial.nct_id,
            "phase": trial.phase,
            "indication": trial.indication,
            "is_pivotal": trial.is_pivotal
        },
        "primary_endpoints": [
            {
                "name": trial.primary_endpoint_text or "Primary Endpoint",
                "evidence": []
            }
        ],
        "populations": {
            "itt": {"defined": True, "evidence": []},
            "pp": {"defined": False, "evidence": []},
            "analysis_primary_on": "ITT"
        },
        "arms": [
            {
                "label": "Treatment",
                "n": None,  # We don't have per-arm enrollment in basic trial data
                "evidence": []
            }
        ],
        "sample_size": {
            "total_n": None,  # We don't have total enrollment in basic trial data
            "evidence": []
        },
        "results": {
            "primary": []
        },
        "coverage_level": "low",
        "coverage_rationale": "Basic trial data only"
    }
    
    return study_card

if __name__ == "__main__":
    success = test_signal_detection()
    if success:
        print("\n✅ Signal detection test completed successfully!")
    else:
        print("\n❌ Signal detection test failed!")
        sys.exit(1)
