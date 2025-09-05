#!/usr/bin/env python3
"""
Run synthesis on extracted data.
"""

import json
import sys
from pathlib import Path

from ncfd.synthesis.evidence_constrained_synthesis import EvidenceConstrainedSynthesis
from ncfd.config import get_config
from ncfd.db.session import get_db_session
from ncfd.db.models import Trial, Study, Signal, Gate, Score
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
    
    # Get signals and gates from database
    try:
        # Load signals from database
        db_signals = session.query(Signal).filter(Signal.trial_id == trial.trial_id).all()
        
        # Convert to SignalResult format expected by gates module
        signals = {}
        for db_signal in db_signals:
            signals[db_signal.s_id] = {
                "fired": db_signal.severity is not None,
                "severity": db_signal.severity,
                "value": float(db_signal.value) if db_signal.value else None,
                "metadata": db_signal.metadata_jsonb or {}
            }
        
        # Load gates from database
        db_gates = session.query(Gate).filter(Gate.trial_id == trial.trial_id).all()
        
        # Convert to GateResult format
        gates = {}
        for db_gate in db_gates:
            gates[db_gate.g_id] = {
                "fired": db_gate.fired_bool,
                "supporting_signals": db_gate.supporting_s_ids,
                "likelihood_ratio": float(db_gate.lr_used) if db_gate.lr_used else None,
                "rationale": db_gate.rationale_text
            }
            
    except Exception as e:
        raise ValueError(f"Failed to load signals/gates for trial {trial_id}: {e}")
    
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
            
            # Load score from database or compute if not available
            try:
                # Try to load existing score from database
                db_score = session.query(Score).filter(
                    Score.trial_id == trial.trial_id
                ).order_by(Score.timestamp.desc()).first()
                
                if db_score:
                    # Use existing score from database
                    score = {
                        "trial_id": trial.trial_id,
                        "run_id": db_score.run_id,
                        "prior_pi": float(db_score.prior_pi) if db_score.prior_pi else None,
                        "logit_prior": float(db_score.logit_prior) if db_score.logit_prior else None,
                        "sum_log_lr": float(db_score.sum_log_lr) if db_score.sum_log_lr else None,
                        "logit_post": float(db_score.logit_post) if db_score.logit_post else None,
                        "p_fail": float(db_score.p_fail) if db_score.p_fail else None,
                        "stop_rule_applied": False  # TODO: Add stop rule tracking to database
                    }
                else:
                    # Compute score if not in database
                    score = compute_score(trial.trial_id, signals, gates)
                    
            except Exception as e:
                raise ValueError(f"Failed to load/compute score for trial {trial.trial_id}: {e}")
            
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
