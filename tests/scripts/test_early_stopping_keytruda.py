#!/usr/bin/env python3
"""
Test early stopping for Keytruda trial.
"""

import json
import sys
from pathlib import Path

from ncfd.pipeline.early_stopping import EarlyStopping
from ncfd.config import get_config


class EarlyStoppingTester:
    """Test early stopping on Keytruda literature."""
    
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
            'trial_id': 'KEYTRUDA_TEST_001',
            'nct_id': 'NCT01295827',  # Keytruda's first major trial
            'asset': 'pembrolizumab',
            'indication': 'melanoma',
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
    
    def simulate_keytruda_literature(self) -> List[Dict[str, Any]]:
        """Simulate Keytruda literature with mostly positive results."""
        
        # Keytruda is a very successful drug with mostly positive trial results
        # These are simulated documents representing typical Keytruda literature
        documents = [
            {
                'pmid': 'sim_001',
                'title': 'Pembrolizumab versus Ipilimumab in Advanced Melanoma',
                'abstract': 'Pembrolizumab demonstrated superior overall survival compared to ipilimumab in patients with advanced melanoma. The primary endpoint was met with statistical significance (p < 0.001).',
                'pub_date': '2015-04-19',
                'article_type': 'RCT',
                'r_score': 0.85,  # High relevance
                's_score': 0.05,  # Very low shortability (success)
                'r_tier': 'R3',
                's_tier': 'S0'
            },
            {
                'pmid': 'sim_002', 
                'title': 'Pembrolizumab for the Treatment of Non-Small-Cell Lung Cancer',
                'abstract': 'Pembrolizumab showed significant improvement in progression-free survival and overall survival compared to chemotherapy. The trial met its primary endpoint.',
                'pub_date': '2016-10-09',
                'article_type': 'RCT',
                'r_score': 0.80,
                's_score': 0.08,
                'r_tier': 'R3',
                's_tier': 'S0'
            },
            {
                'pmid': 'sim_003',
                'title': 'Pembrolizumab in Advanced Urothelial Carcinoma',
                'abstract': 'Pembrolizumab demonstrated robust antitumor activity with manageable safety profile. Primary endpoint was met with strong statistical significance.',
                'pub_date': '2017-03-16',
                'article_type': 'RCT',
                'r_score': 0.75,
                's_score': 0.06,
                'r_tier': 'R2',
                's_tier': 'S0'
            },
            {
                'pmid': 'sim_004',
                'title': 'Pembrolizumab versus Chemotherapy for PD-L1-Positive NSCLC',
                'abstract': 'Pembrolizumab significantly improved overall survival compared to chemotherapy. The benefit was consistent across all subgroups analyzed.',
                'pub_date': '2016-10-09',
                'article_type': 'RCT',
                'r_score': 0.82,
                's_score': 0.04,
                'r_tier': 'R3',
                's_tier': 'S0'
            },
            {
                'pmid': 'sim_005',
                'title': 'Pembrolizumab for Advanced Melanoma: Long-term Follow-up',
                'abstract': 'Long-term follow-up confirms sustained benefit of pembrolizumab with 5-year overall survival rate of 34%. No new safety signals identified.',
                'pub_date': '2019-06-04',
                'article_type': 'Results',
                'r_score': 0.78,
                's_score': 0.03,
                'r_tier': 'R2',
                's_tier': 'S0'
            },
            {
                'pmid': 'sim_006',
                'title': 'Pembrolizumab in Combination with Chemotherapy for NSCLC',
                'abstract': 'Pembrolizumab plus chemotherapy demonstrated superior efficacy compared to chemotherapy alone. Primary endpoint met with strong statistical significance.',
                'pub_date': '2018-04-16',
                'article_type': 'RCT',
                'r_score': 0.76,
                's_score': 0.07,
                'r_tier': 'R2',
                's_tier': 'S0'
            },
            {
                'pmid': 'sim_007',
                'title': 'Pembrolizumab for Advanced Head and Neck Cancer',
                'abstract': 'Pembrolizumab showed significant improvement in overall survival compared to standard therapy. The trial met its primary endpoint with robust results.',
                'pub_date': '2016-08-25',
                'article_type': 'RCT',
                'r_score': 0.74,
                's_score': 0.05,
                'r_tier': 'R2',
                's_tier': 'S0'
            },
            {
                'pmid': 'sim_008',
                'title': 'Pembrolizumab in Advanced Gastric Cancer',
                'abstract': 'Pembrolizumab demonstrated clinically meaningful benefit in patients with advanced gastric cancer. Primary endpoint was met with statistical significance.',
                'pub_date': '2017-06-06',
                'article_type': 'RCT',
                'r_score': 0.71,
                's_score': 0.09,
                'r_tier': 'R2',
                's_tier': 'S0'
            },
            {
                'pmid': 'sim_009',
                'title': 'Pembrolizumab for Advanced Renal Cell Carcinoma',
                'abstract': 'Pembrolizumab plus axitinib showed superior progression-free survival compared to sunitinib. Primary endpoint met with strong statistical significance.',
                'pub_date': '2019-02-16',
                'article_type': 'RCT',
                'r_score': 0.73,
                's_score': 0.06,
                'r_tier': 'R2',
                's_tier': 'S0'
            },
            {
                'pmid': 'sim_010',
                'title': 'Pembrolizumab in Advanced Esophageal Cancer',
                'abstract': 'Pembrolizumab demonstrated significant improvement in overall survival compared to chemotherapy. The trial met its primary endpoint with robust results.',
                'pub_date': '2019-07-30',
                'article_type': 'RCT',
                'r_score': 0.70,
                's_score': 0.08,
                'r_tier': 'R2',
                's_tier': 'S0'
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
        # For Keytruda, we expect mostly low shortability scores
        self._update_p_short(document)
        
        # Update expected utility (should decrease as we see more positive results)
        self._update_expected_utility()
        
        # Update processing time
        self.trial_state['processing_time'] += 0.1  # Simulate processing time
    
    def _update_p_short(self, document: Dict[str, Any]):
        """Update p_short based on new document evidence."""
        # For Keytruda, we expect mostly S0 scores (successful trials)
        # p_short should remain low as we see more positive results
        
        current_p_short = self.trial_state['p_short']
        
        # Weight the new evidence based on relevance
        if document['r_tier'] in ['R3', 'R2']:
            weight = 0.15  # High relevance documents have more weight
        else:
            weight = 0.05  # Lower relevance documents have less weight
        
        # Update p_short: for successful drugs, it should stay low
        new_contribution = document['s_score'] * weight
        self.trial_state['p_short'] = current_p_short + new_contribution
        
        # Keep p_short bounded between 0 and 1
        self.trial_state['p_short'] = max(0.0, min(1.0, self.trial_state['p_short']))
        
        # Store in history for plateau detection
        self.trial_state['p_short_history'].append(self.trial_state['p_short'])
    
    def _update_expected_utility(self):
        """Update expected utility of next document."""
        # For Keytruda, as we see more positive results, expected utility should decrease
        # because additional documents are unlikely to change the low shortability assessment
        
        current_p_short = self.trial_state['p_short']
        n_docs_seen = self.trial_state['n_docs_seen']
        
        # Expected utility decreases as we see more consistent positive results
        if current_p_short < 0.15 and n_docs_seen > 5:
            # Very low shortability with multiple documents
            self.trial_state['max_expected_utility_next_doc'] = 0.02
        elif current_p_short < 0.25 and n_docs_seen > 3:
            # Low shortability with some documents
            self.trial_state['max_expected_utility_next_doc'] = 0.05
        else:
            # Still some uncertainty
            self.trial_state['max_expected_utility_next_doc'] = 0.1
    
    def test_early_stopping(self):
        """Test early stopping on Keytruda literature."""
        print("🔬 Testing Early Stopping on Keytruda (Pembrolizumab)")
        print("=" * 60)
        print(f"📋 Trial: {self.trial_state['trial_id']}")
        print(f"💊 Drug: {self.trial_state['asset']}")
        print(f"🎯 Indication: {self.trial_state['indication']}")
        print()
        
        # Simulate Keytruda literature
        documents = self.simulate_keytruda_literature()
        
        print("📚 Processing Keytruda Literature...")
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
        if final_decision in ["park", "stop"] and self.trial_state['p_short'] < 0.25:
            print("✅ CORRECT: System correctly early stopped for successful drug")
            print("✅ Keytruda shows low shortability scores as expected")
        elif final_decision == "promote":
            print("❌ INCORRECT: System should not promote successful drug")
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
    """Run the Keytruda early stopping test."""
    print("🚀 Keytruda Early Stopping Test")
    print("=" * 60)
    print("Testing that the system correctly early stops when processing")
    print("literature for a highly successful drug (Keytruda/pembrolizumab)")
    print()
    
    tester = EarlyStoppingTester()
    results = tester.test_early_stopping()
    
    # Save results
    output_file = Path("backtest/keytruda_early_stopping_test.json")
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump({
            'test_info': {
                'date': datetime.now().isoformat(),
                'test_type': 'early_stopping_keytruda',
                'description': 'Test early stopping on successful drug Keytruda'
            },
            'results': results
        }, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    print("\n✅ Test completed!")


if __name__ == "__main__":
    main()
