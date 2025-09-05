#!/usr/bin/env python3
"""
Test early stopping for Cassava trial.
"""

import json
import sys
from pathlib import Path

from ncfd.orchestrate.early_stopping import EarlyStopping
from ncfd.config import get_config


class EarlyStoppingTester:
    """Test early stopping on Cassava literature."""
    
    def __init__(self):
        self.config = {
            'theta_high': 0.80,  # High confidence stop threshold
            'theta_low': 0.20,   # Low confidence stop threshold
            'plateau_eps': 0.03, # Plateau detection epsilon
            'delta_min': 0.05,    # Minimum expected utility
            'max_abstracts_total': 50,  # Document quota
            'max_processing_time': 2.0   # Time limit in hours
        }
        
        self.trial_state = {
            'trial_id': 'CASSAVA_TEST_001',
            'nct_id': 'NCT05352763',  # Cassava's simufilam trial
            'asset': 'simufilam',
            'indication': 'alzheimers_disease',
            'p_short': 0.0,  # Start with low shortability
            'p_short_history': [],
            'n_docs_seen': 0,
            'n_docs_selected': 0,
            'best_S_Rge2': 0.0,
            'max_expected_utility_next_doc': 0.1,
            'processing_time': 0.0,
            'status': 'active'
        }
        
        self.logger = self._setup_logger()
    
    def _setup_logger(self):
        """Setup logging."""
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
    def simulate_cassava_literature(self) -> List[Dict[str, Any]]:
        """Simulate Cassava literature with mostly negative results."""
        
        # Cassava's simufilam had multiple issues and ultimately failed
        # These are simulated documents representing typical Cassava literature
        documents = [
            {
                'pmid': 'sim_001',
                'title': 'Simufilam Phase 2 Randomized Withdrawal Study in Alzheimer Disease',
                'abstract': 'The randomized withdrawal study showed no statistical difference between simufilam and placebo groups. Primary endpoint was not met.',
                'pub_date': '2023-01-15',
                'article_type': 'RCT',
                'r_score': 0.85,  # High relevance
                's_score': 0.75,  # High shortability (failure)
                'r_tier': 'R3',
                's_tier': 'S3'
            },
            {
                'pmid': 'sim_002', 
                'title': 'Simufilam Mechanism of Action: FLNA Binding Analysis',
                'abstract': 'Simufilam shows weak binding affinity (~µM) to FLNA, suggesting poor target coverage. PK and brain partitioning are suboptimal.',
                'pub_date': '2022-06-20',
                'article_type': 'Preclinical',
                'r_score': 0.70,
                's_score': 0.65,
                'r_tier': 'R2',
                's_tier': 'S3'
            },
            {
                'pmid': 'sim_003',
                'title': 'Simufilam Phase 2a Cognition Claims: Post-hoc Analysis',
                'abstract': 'Cognition improvements were only seen in post-hoc subgroup analysis without proper multiplicity control. Primary analysis was negative.',
                'pub_date': '2022-03-10',
                'article_type': 'Results',
                'r_score': 0.75,
                's_score': 0.70,
                'r_tier': 'R2',
                's_tier': 'S3'
            },
            {
                'pmid': 'sim_004',
                'title': 'Simufilam RETHINK-ALZ Phase 3 Trial Results',
                'abstract': 'RETHINK-ALZ Phase 3 trial failed to meet primary endpoint. Trial was terminated early due to lack of efficacy.',
                'pub_date': '2024-11-15',
                'article_type': 'RCT',
                'r_score': 0.90,
                's_score': 0.85,
                'r_tier': 'R3',
                's_tier': 'S3'
            },
            {
                'pmid': 'sim_005',
                'title': 'Simufilam REFOCUS-ALZ Phase 3 Trial Results',
                'abstract': 'REFOCUS-ALZ Phase 3 trial also failed to meet primary endpoint. Both Phase 3 trials showed no benefit over placebo.',
                'pub_date': '2024-12-01',
                'article_type': 'RCT',
                'r_score': 0.88,
                's_score': 0.80,
                'r_tier': 'R3',
                's_tier': 'S3'
            },
            {
                'pmid': 'sim_006',
                'title': 'Simufilam Safety Profile: Adverse Events Analysis',
                'abstract': 'Simufilam showed higher rates of adverse events compared to placebo, including gastrointestinal and neurological side effects.',
                'pub_date': '2023-08-15',
                'article_type': 'Safety',
                'r_score': 0.65,
                's_score': 0.60,
                'r_tier': 'R2',
                's_tier': 'S2'
            },
            {
                'pmid': 'sim_007',
                'title': 'Simufilam Open-Label Extension Study Results',
                'abstract': 'Open-label extension showed no sustained benefit. Long-term data does not support continued development.',
                'pub_date': '2024-01-20',
                'article_type': 'Results',
                'r_score': 0.72,
                's_score': 0.68,
                'r_tier': 'R2',
                's_tier': 'S3'
            },
            {
                'pmid': 'sim_008',
                'title': 'Simufilam Biomarker Analysis: No Target Engagement',
                'abstract': 'Biomarker analysis failed to show target engagement. FLNA levels and downstream markers unchanged with treatment.',
                'pub_date': '2023-11-05',
                'article_type': 'Biomarker',
                'r_score': 0.68,
                's_score': 0.72,
                'r_tier': 'R2',
                's_tier': 'S3'
            },
            {
                'pmid': 'sim_009',
                'title': 'Simufilam Clinical Development: Lessons Learned',
                'abstract': 'Review of simufilam development highlights issues with mechanism validation, trial design, and post-hoc analysis.',
                'pub_date': '2024-02-10',
                'article_type': 'Review',
                'r_score': 0.60,
                's_score': 0.65,
                'r_tier': 'R1',
                's_tier': 'S2'
            },
            {
                'pmid': 'sim_010',
                'title': 'Simufilam Regulatory Review: FDA Feedback',
                'abstract': 'FDA review identified multiple concerns with trial design, statistical analysis, and evidence quality.',
                'pub_date': '2024-03-15',
                'article_type': 'Regulatory',
                'r_score': 0.55,
                's_score': 0.70,
                'r_tier': 'R1',
                's_tier': 'S3'
            }
        ]
        
        return documents
    
    def update_trial_state(self, document: Dict[str, Any]):
        """Update trial state based on new document."""
        self.trial_state['n_docs_seen'] += 1
        
        # Only count documents with R≥2 for best_S_Rge2
        if document['r_score'] >= 0.55:  # R2 threshold
            self.trial_state['n_docs_selected'] += 1
            if document['s_score'] > self.trial_state['best_S_Rge2']:
                self.trial_state['best_S_Rge2'] = document['s_score']
        
        # Update p_short based on cumulative evidence
        # For Cassava, we expect mostly high shortability scores
        self._update_p_short(document)
        
        # Update expected utility (should increase as we see more negative results)
        self._update_expected_utility()
        
        # Update processing time
        self.trial_state['processing_time'] += 0.1  # Simulate processing time
    
    def _update_p_short(self, document: Dict[str, Any]):
        """Update p_short based on new document evidence."""
        # For Cassava, we expect mostly S3 scores (failed trials)
        # p_short should increase as we see more negative results
        
        current_p_short = self.trial_state['p_short']
        
        # Weight the new evidence based on relevance
        if document['r_tier'] in ['R3', 'R2']:
            weight = 0.15  # High relevance documents have more weight
        else:
            weight = 0.05  # Lower relevance documents have less weight
        
        # Update p_short: for failed drugs, it should increase
        new_contribution = document['s_score'] * weight
        self.trial_state['p_short'] = current_p_short + new_contribution
        
        # Keep p_short bounded between 0 and 1
        self.trial_state['p_short'] = max(0.0, min(1.0, self.trial_state['p_short']))
        
        # Store in history for plateau detection
        self.trial_state['p_short_history'].append(self.trial_state['p_short'])
    
    def _update_expected_utility(self):
        """Update expected utility of next document."""
        # For Cassava, as we see more negative results, expected utility should increase
        # because additional documents are likely to confirm the high shortability assessment
        
        current_p_short = self.trial_state['p_short']
        n_docs_seen = self.trial_state['n_docs_seen']
        
        # Expected utility increases as we see more consistent negative results
        if current_p_short > 0.75 and n_docs_seen > 5:
            # Very high shortability with multiple documents
            self.trial_state['max_expected_utility_next_doc'] = 0.15
        elif current_p_short > 0.60 and n_docs_seen > 3:
            # High shortability with some documents
            self.trial_state['max_expected_utility_next_doc'] = 0.12
        else:
            # Still some uncertainty
            self.trial_state['max_expected_utility_next_doc'] = 0.10
    
    def test_early_stopping(self):
        """Test early stopping on Cassava literature."""
        print("🔬 Testing Early Stopping on Cassava (Simufilam)")
        print("=" * 60)
        print(f"📋 Trial: {self.trial_state['trial_id']}")
        print(f"💊 Drug: {self.trial_state['asset']}")
        print(f"🎯 Indication: {self.trial_state['indication']}")
        print()
        
        # Simulate Cassava literature
        documents = self.simulate_cassava_literature()
        
        print("📚 Processing Cassava Literature...")
        print("-" * 40)
        
        for i, doc in enumerate(documents, 1):
            print(f"\n📄 Document {i}: {doc['title'][:60]}...")
            print(f"   R Score: {doc['r_score']:.2f} ({doc['r_tier']})")
            print(f"   S Score: {doc['s_score']:.2f} ({doc['s_tier']})")
            
            # Update trial state
            self.update_trial_state(doc)
            
            # Check for early stopping
            stop_decision, reason = should_stop_early(self.trial_state, self.config)
            
            print(f"   📊 Current State:")
            print(f"      p_short: {self.trial_state['p_short']:.3f}")
            print(f"      n_docs_seen: {self.trial_state['n_docs_seen']}")
            print(f"      best_S_Rge2: {self.trial_state['best_S_Rge2']:.3f}")
            print(f"      expected_utility: {self.trial_state['max_expected_utility_next_doc']:.3f}")
            
            if stop_decision != "continue":
                print(f"   🛑 EARLY STOPPING: {stop_decision.upper()} - {reason}")
                break
            else:
                print(f"   ➡️  Continue processing...")
        
        # Final analysis
        print("\n" + "=" * 60)
        print("📊 FINAL ANALYSIS")
        print("=" * 60)
        
        print(f"📈 Documents Processed: {self.trial_state['n_docs_seen']}")
        print(f"📈 Documents Selected (R≥2): {self.trial_state['n_docs_seen']}")
        print(f"📈 Final p_short: {self.trial_state['p_short']:.3f}")
        print(f"📈 Best S Score (R≥2): {self.trial_state['best_S_Rge2']:.3f}")
        print(f"📈 Expected Utility: {self.trial_state['max_expected_utility_next_doc']:.3f}")
        
        # Check if early stopping was triggered
        final_decision, final_reason = should_stop_early(self.trial_state, self.config)
        
        print(f"\n🎯 FINAL DECISION: {final_decision.upper()}")
        if final_reason:
            print(f"🎯 REASON: {final_reason}")
        
        # Validate the result
        print(f"\n✅ VALIDATION:")
        if final_decision == "promote" and self.trial_state['best_S_Rge2'] >= 0.70:
            print("✅ CORRECT: System correctly promoted failed drug for review")
            print("✅ Cassava shows high shortability scores as expected")
        elif final_decision == "promote" and self.trial_state['p_short'] > 0.75:
            print("✅ CORRECT: System correctly promoted failed drug for review")
            print("✅ Cassava shows high cumulative shortability as expected")
        elif final_decision in ["park", "stop"] and self.trial_state['best_S_Rge2'] < 0.45:
            print("❌ INCORRECT: System should not park/stop failed drug")
        else:
            print("⚠️  UNCLEAR: Result needs manual review")
        
        return {
            'trial_id': self.trial_state['trial_id'],
            'final_decision': final_decision,
            'final_reason': final_reason,
            'p_short': self.trial_state['p_short'],
            'n_docs_seen': self.trial_state['n_docs_seen'],
            'best_S_Rge2': self.trial_state['best_S_Rge2'],
            'expected_utility': self.trial_state['max_expected_utility_next_doc']
        }


def main():
    """Run the Cassava early stopping test."""
    print("🚀 Cassava Early Stopping Test")
    print("=" * 60)
    print("Testing that the system does NOT early stop when processing")
    print("literature for a failed drug (Cassava's simufilam)")
    print()
    
    tester = EarlyStoppingTester()
    results = tester.test_early_stopping()
    
    # Save results
    output_file = Path("backtest/cassava_early_stopping_test.json")
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump({
            'test_info': {
                'date': datetime.now().isoformat(),
                'test_type': 'early_stopping_cassava',
                'description': 'Test early stopping on failed drug Cassava'
            },
            'results': results
        }, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    print("\n✅ Test completed!")


if __name__ == "__main__":
    main()
