#!/usr/bin/env python3
"""
Test top-k guard functionality.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

from ncfd.signals.gates import TopKGuard
from ncfd.config import get_config


class TopKGuardTester:
    """Test Top-K guard on mixed literature."""
    
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
            'trial_id': 'MIXED_TEST_001',
            'nct_id': 'NCT01234567',
            'asset': 'test_drug',
            'indication': 'test_indication',
            'p_short': 0.0,  # Start with low shortability
            'p_short_history': [],
            'n_docs_seen': 0,
            'n_docs_selected': 0,
            'best_S_Rge2': 0.0,
            'max_expected_utility_next_doc': 0.1,
            'processing_time': 0.0,
            'status': 'active'
        }
        
        # Initialize Top-K guard
        self.trial_state = TopKGuard.initialize_top_k_guard(self.trial_state, k=10)
        
        self.logger = self._setup_logger()
    
    def _setup_logger(self):
        """Setup logging."""
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
    def simulate_mixed_literature(self) -> List[Dict[str, Any]]:
        """Simulate literature with mixed results (some promising, some risky)."""
        
        # This simulates a trial where the top 10 documents have mixed signals
        # Some show promising results, but one shows clear risk signals
        documents = [
            # Top-K documents (ranked by relevance)
            {
                'pmid': 'top_001',
                'title': 'Promising Phase 2 Results for Test Drug',
                'abstract': 'Test drug showed significant improvement in primary endpoint with p < 0.001.',
                'pub_date': '2024-01-15',
                'article_type': 'RCT',
                'r_score': 0.85,  # High relevance
                's_score': 0.05,  # Low shortability (promising)
                'r_tier': 'R3',
                's_tier': 'S0',
                'is_top_k': True
            },
            {
                'pmid': 'top_002',
                'title': 'Test Drug Safety Profile Analysis',
                'abstract': 'Test drug demonstrated excellent safety profile with minimal adverse events.',
                'pub_date': '2024-02-01',
                'article_type': 'Safety',
                'r_score': 0.80,
                's_score': 0.08,
                'r_tier': 'R3',
                's_tier': 'S0',
                'is_top_k': True
            },
            {
                'pmid': 'top_003',
                'title': 'Test Drug Mechanism of Action Study',
                'abstract': 'Test drug showed robust target engagement and mechanism validation.',
                'pub_date': '2024-02-15',
                'article_type': 'Preclinical',
                'r_score': 0.75,
                's_score': 0.06,
                'r_tier': 'R2',
                's_tier': 'S0',
                'is_top_k': True
            },
            {
                'pmid': 'top_004',
                'title': 'Test Drug Phase 1 Results',
                'abstract': 'Phase 1 study demonstrated good pharmacokinetics and tolerability.',
                'pub_date': '2024-03-01',
                'article_type': 'RCT',
                'r_score': 0.70,
                's_score': 0.07,
                'r_tier': 'R2',
                's_tier': 'S0',
                'is_top_k': True
            },
            {
                'pmid': 'top_005',
                'title': 'Test Drug Biomarker Analysis',
                'abstract': 'Biomarker analysis showed consistent target engagement across patient subgroups.',
                'pub_date': '2024-03-15',
                'article_type': 'Biomarker',
                'r_score': 0.72,
                's_score': 0.05,
                'r_tier': 'R2',
                's_tier': 'S0',
                'is_top_k': True
            },
            {
                'pmid': 'top_006',
                'title': 'Test Drug Subgroup Analysis Reveals Concerns',
                'abstract': 'Subgroup analysis showed primary endpoint was not met in key patient population. Post-hoc analysis revealed significant safety concerns.',
                'pub_date': '2024-04-01',
                'article_type': 'RCT',
                'r_score': 0.88,  # Very high relevance
                's_score': 0.75,  # High shortability (RISKY!)
                'r_tier': 'R3',
                's_tier': 'S3',
                'is_top_k': True
            },
            {
                'pmid': 'top_007',
                'title': 'Test Drug Long-term Follow-up',
                'abstract': 'Long-term follow-up confirms sustained benefit with 2-year data.',
                'pub_date': '2024-04-15',
                'article_type': 'Results',
                'r_score': 0.78,
                's_score': 0.04,
                'r_tier': 'R2',
                's_tier': 'S0',
                'is_top_k': True
            },
            {
                'pmid': 'top_008',
                'title': 'Test Drug Combination Therapy Study',
                'abstract': 'Combination therapy showed additive effects without increased toxicity.',
                'pub_date': '2024-05-01',
                'article_type': 'RCT',
                'r_score': 0.73,
                's_score': 0.06,
                'r_tier': 'R2',
                's_tier': 'S0',
                'is_top_k': True
            },
            {
                'pmid': 'top_009',
                'title': 'Test Drug Quality of Life Analysis',
                'abstract': 'Quality of life measures showed significant improvement in treated patients.',
                'pub_date': '2024-05-15',
                'article_type': 'QoL',
                'r_score': 0.65,
                's_score': 0.05,
                'r_tier': 'R2',
                's_tier': 'S0',
                'is_top_k': True
            },
            {
                'pmid': 'top_010',
                'title': 'Test Drug Cost-effectiveness Analysis',
                'abstract': 'Cost-effectiveness analysis supports favorable economic profile.',
                'pub_date': '2024-06-01',
                'article_type': 'Economic',
                'r_score': 0.60,
                's_score': 0.03,
                'r_tier': 'R1',
                's_tier': 'S0',
                'is_top_k': True
            },
            # Non-Top-K documents (lower relevance)
            {
                'pmid': 'other_001',
                'title': 'Test Drug in Different Indication',
                'abstract': 'Test drug showed mixed results in different indication.',
                'pub_date': '2024-06-15',
                'article_type': 'RCT',
                'r_score': 0.45,  # Lower relevance
                's_score': 0.30,  # Medium shortability
                'r_tier': 'R1',
                's_tier': 'S2',
                'is_top_k': False
            },
            {
                'pmid': 'other_002',
                'title': 'Test Drug Review Article',
                'abstract': 'Comprehensive review of test drug development.',
                'pub_date': '2024-07-01',
                'article_type': 'Review',
                'r_score': 0.50,
                's_score': 0.15,
                'r_tier': 'R1',
                's_tier': 'S1',
                'is_top_k': False
            }
        ]
        
        return documents
    
    def test_top_k_guard(self):
        """Test Top-K guard mechanism."""
        print("🔬 Testing Top-K Guard Mechanism")
        print("=" * 60)
        print(f"📋 Trial: {self.trial_state['trial_id']}")
        print(f"💊 Drug: {self.trial_state['asset']}")
        print(f"🎯 Indication: {self.trial_state['indication']}")
        print(f"🔒 Top-K Guard: {self.trial_state['top_k_guard']['k']} documents")
        print()
        
        # Simulate mixed literature
        documents = self.simulate_mixed_literature()
        
        print("📚 Processing Mixed Literature (Top-K + Others)...")
        print("-" * 50)
        
        risk_hit_detected = False
        
        for i, doc in enumerate(documents, 1):
            print(f"\n📄 Document {i}: {doc['title'][:50]}...")
            print(f"   R Score: {doc['r_score']:.2f} ({doc['r_tier']})")
            print(f"   S Score: {doc['s_score']:.2f} ({doc['s_tier']})")
            print(f"   Top-K: {'✅' if doc['is_top_k'] else '❌'}")
            
            # Update trial state
            self.trial_state = TopKGuard.update_trial_state(
                self.trial_state, 
                doc, 
                is_top_k=doc['is_top_k']
            )
            
            # Check for early stopping
            stop_decision, reason = TopKGuard.should_stop_early(self.trial_state, self.config)
            
            print(f"   📊 Current State:")
            print(f"      p_short: {self.trial_state['p_short']:.3f}")
            print(f"      n_docs_seen: {self.trial_state['n_docs_seen']}")
            print(f"      best_S_Rge2: {self.trial_state['best_S_Rge2']:.3f}")
            print(f"      Top-K seen: {self.trial_state['top_k_guard']['seen']}")
            print(f"      Top-K risk_hit: {self.trial_state['top_k_guard']['risk_hit']}")
            print(f"      Top-K completed: {self.trial_state['top_k_guard']['completed']}")
            
            if stop_decision != "continue":
                print(f"   🛑 EARLY STOPPING: {stop_decision.upper()} - {reason}")
                
                # Check if this is the expected behavior
                if reason == "top_k_risk_guard":
                    risk_hit_detected = True
                    print(f"   ✅ CORRECT: Top-K guard prevented parking due to risk signal")
                elif reason == "top_k_incomplete":
                    print(f"   ✅ CORRECT: Top-K guard prevented parking due to incomplete review")
                elif reason == "high_shortability_score":
                    print(f"   ✅ CORRECT: High S score triggered promotion")
                elif reason == "low_confidence" and self.trial_state['top_k_guard']['completed']:
                    print(f"   ✅ CORRECT: Parking allowed after Top-K completion")
                else:
                    print(f"   ⚠️  UNEXPECTED: {reason}")
                
                break
            else:
                print(f"   ➡️  Continue processing...")
        
        # Final analysis
        print("\n" + "=" * 60)
        print("📊 FINAL ANALYSIS")
        print("=" * 60)
        
        print(f"📈 Documents Processed: {self.trial_state['n_docs_seen']}")
        print(f"📈 Top-K Documents Seen: {self.trial_state['top_k_guard']['seen']}")
        print(f"📈 Top-K Risk Hit: {self.trial_state['top_k_guard']['risk_hit']}")
        print(f"📈 Top-K Completed: {self.trial_state['top_k_guard']['completed']}")
        print(f"📈 Final p_short: {self.trial_state['p_short']:.3f}")
        print(f"📈 Best S Score (R≥2): {self.trial_state['best_S_Rge2']:.3f}")
        
        # Check final decision
        final_decision, final_reason = TopKGuard.should_stop_early(self.trial_state, self.config)
        
        print(f"\n🎯 FINAL DECISION: {final_decision.upper()}")
        if final_reason:
            print(f"🎯 REASON: {final_reason}")
        
        # Validate the result
        print(f"\n✅ VALIDATION:")
        if risk_hit_detected:
            print("✅ CORRECT: Top-K guard successfully detected risk signal")
            print("✅ System prevented premature parking despite promising documents")
        elif final_decision == "park" and self.trial_state['top_k_guard']['completed']:
            print("✅ CORRECT: System allowed parking after Top-K completion")
        elif final_decision == "promote":
            print("✅ CORRECT: System promoted trial due to high S score")
        else:
            print("⚠️  UNCLEAR: Result needs manual review")
        
        return {
            'trial_id': self.trial_state['trial_id'],
            'final_decision': final_decision,
            'final_reason': final_reason,
            'p_short': self.trial_state['p_short'],
            'n_docs_seen': self.trial_state['n_docs_seen'],
            'best_S_Rge2': self.trial_state['best_S_Rge2'],
            'top_k_seen': self.trial_state['top_k_guard']['seen'],
            'top_k_risk_hit': self.trial_state['top_k_guard']['risk_hit'],
            'top_k_completed': self.trial_state['top_k_guard']['completed']
        }


def main():
    """Run the Top-K guard test."""
    print("🚀 Top-K Guard Test")
    print("=" * 60)
    print("Testing that the system correctly prevents early parking when")
    print("there are risk signals in the top-K most relevant documents")
    print()
    
    tester = TopKGuardTester()
    results = tester.test_top_k_guard()
    
    # Save results
    output_file = Path("backtest/top_k_guard_test.json")
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump({
            'test_info': {
                'date': datetime.now().isoformat(),
                'test_type': 'top_k_guard',
                'description': 'Test Top-K guard mechanism with mixed literature'
            },
            'results': results
        }, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    print("\n✅ Test completed!")


if __name__ == "__main__":
    main()
