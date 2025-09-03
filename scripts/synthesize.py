#!/usr/bin/env python3
"""
CLI script for running deterministic synthesis on trials.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.synthesis.evidence_constrained_synthesis import EvidenceConstrainedSynthesizer, SynthesisError, GPT5ThinkingHook
from ncfd.db.session import get_db_session
from ncfd.db.models import Trial, Study
from ncfd.signals.gates import get_gate_results
from ncfd.signals.scoring import compute_score


def load_trial_data(trial_id: str, session) -> tuple[Trial, list[Study], dict, dict]:
    """Load trial data from database."""
    # Get trial
    trial = session.query(Trial).filter(Trial.trial_id == trial_id).first()
    if not trial:
        raise ValueError(f"Trial {trial_id} not found")
    
    # Get study cards
    study_cards = session.query(Study).filter(Study.trial_id == trial_id).all()
    
    # Get signals and gates (you'll need to implement these based on your existing code)
    # For now, we'll create placeholder data
    signals = {}  # TODO: Load from your signals table
    gates = get_gate_results(signals)  # TODO: Implement based on your gates module
    
    return trial, study_cards, signals, gates


def main():
    parser = argparse.ArgumentParser(description="Generate deterministic synthesis for a trial")
    parser.add_argument("--trial-id", required=True, help="Trial ID to synthesize")
    parser.add_argument("--config", help="Path to synthesis config file")
    parser.add_argument("--out", help="Output file path (default: stdout)")
    parser.add_argument("--trigger-gpt5", action="store_true", help="Force GPT-5 analysis regardless of threshold")
    parser.add_argument("--gpt5-api-key", help="GPT-5 API key for thinking model")
    
    args = parser.parse_args()
    
    try:
        # Initialize synthesizer
        synthesizer = EvidenceConstrainedSynthesizer(config_path=args.config)
        
        # Get database session
        with get_db_session() as session:
            # Load trial data
            trial, study_cards, signals, gates = load_trial_data(args.trial_id, session)
            
            # Compute score
            score = compute_score(trial.trial_id, signals, gates)  # TODO: Implement based on your scoring module
            
            # Generate synthesis
            synthesis_doc = synthesizer.generate(trial, study_cards, gates, score)
            
            # Trigger GPT-5 if needed
            if args.trigger_gpt5 or synthesis_doc.gpt5_hook_triggered:
                gpt5_hook = GPT5ThinkingHook(api_key=args.gpt5_api_key)
                gpt5_analysis = gpt5_hook.trigger_thinking_analysis(
                    trial_id=trial.trial_id,
                    nct_id=trial.nct_id,
                    indication=trial.indication,
                    p_fail=score.p_fail
                )
                synthesis_doc.audit["gpt5_analysis"] = gpt5_analysis
            
            # Output result
            output_data = synthesis_doc.dict()
            
            if args.out:
                output_path = Path(args.out)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w') as f:
                    json.dump(output_data, f, indent=2)
                print(f"Synthesis written to {output_path}")
            else:
                print(json.dumps(output_data, indent=2))
                
    except SynthesisError as e:
        print(f"Synthesis Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
