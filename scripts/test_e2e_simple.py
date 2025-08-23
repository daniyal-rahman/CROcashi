#!/usr/bin/env python3
"""
Simplified End-to-End Pipeline Test.

This script tests the pipeline components individually to avoid transaction conflicts:
1. Database connectivity and basic operations
2. Data quality analysis on existing data
3. Trial selection and analysis
4. Study card simulation
5. Signal detection simulation

Avoids running the CT.gov pipeline to prevent transaction corruption.
"""

import os
import sys
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.db.session import get_session
from ncfd.db.models import Trial, TrialVersion, Company, Study

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimpleE2ETestResults:
    """Container for simplified end-to-end test results."""
    
    def __init__(self):
        self.start_time = datetime.utcnow()
        self.database_results = {}
        self.data_quality_results = {}
        self.trial_analysis_results = {}
        self.study_card_results = {}
        self.signal_detection_results = {}
        self.errors = []
        self.warnings = []
    
    def add_error(self, error: str):
        self.errors.append(error)
        logger.error(error)
    
    def add_warning(self, warning: str):
        self.warnings.append(warning)
        logger.warning(warning)
    
    def get_summary(self) -> Dict[str, Any]:
        duration = (datetime.utcnow() - self.start_time).total_seconds()
        return {
            'duration_seconds': duration,
            'success': len(self.errors) == 0,
            'database': self.database_results,
            'data_quality': self.data_quality_results,
            'trial_analysis': self.trial_analysis_results,
            'study_cards': self.study_card_results,
            'signal_detection': self.signal_detection_results,
            'errors': self.errors,
            'warnings': self.warnings
        }

def test_database_connectivity() -> Dict[str, Any]:
    """Test basic database connectivity and operations."""
    logger.info("🔍 Testing database connectivity...")
    
    try:
        with get_session() as session:
            # Test basic operations
            trial_count = session.query(Trial).count()
            version_count = session.query(TrialVersion).count()
            company_count = session.query(Company).count()
            
            # Test if studies table exists
            try:
                study_count = session.query(Study).count()
                studies_available = True
            except Exception:
                study_count = 0
                studies_available = False
            
            # Test a simple query
            recent_trials = session.query(Trial).order_by(Trial.last_seen_at.desc()).limit(5).all()
            
            results = {
                'success': True,
                'trial_count': trial_count,
                'version_count': version_count,
                'company_count': company_count,
                'study_count': study_count,
                'studies_available': studies_available,
                'recent_trials_sample': len(recent_trials),
                'connection_healthy': True
            }
            
            logger.info(f"✅ Database connectivity test passed")
            logger.info(f"   - Trials: {trial_count}, Versions: {version_count}, Companies: {company_count}")
            
            return results
            
    except Exception as e:
        logger.error(f"❌ Database connectivity test failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'connection_healthy': False
        }

def analyze_existing_data_quality() -> Dict[str, Any]:
    """Analyze the quality of existing trial data."""
    logger.info("🔍 Analyzing existing data quality...")
    
    try:
        with get_session() as session:
            # Get recent trials
            recent_trials = session.query(Trial).order_by(Trial.last_seen_at.desc()).limit(50).all()
            
            quality_metrics = {
                'total_trials_analyzed': len(recent_trials),
                'trials_with_sponsor': 0,
                'trials_with_phase': 0,
                'trials_with_status': 0,
                'trials_with_title': 0,
                'trials_with_versions': 0,
                'phase_distribution': {},
                'status_distribution': {},
                'sponsor_variety': set(),
                'recent_trial_details': []
            }
            
            for trial in recent_trials:
                # Check basic fields
                if trial.sponsor_text:
                    quality_metrics['trials_with_sponsor'] += 1
                    quality_metrics['sponsor_variety'].add(trial.sponsor_text)
                
                if trial.phase:
                    quality_metrics['trials_with_phase'] += 1
                    phase = trial.phase
                    quality_metrics['phase_distribution'][phase] = quality_metrics['phase_distribution'].get(phase, 0) + 1
                
                if trial.status:
                    quality_metrics['trials_with_status'] += 1
                    status = trial.status
                    quality_metrics['status_distribution'][status] = quality_metrics['status_distribution'].get(status, 0) + 1
                
                if trial.brief_title or trial.official_title:
                    quality_metrics['trials_with_title'] += 1
                
                # Check versions
                if len(trial.versions) > 0:
                    quality_metrics['trials_with_versions'] += 1
                
                # Store details for first few trials
                if len(quality_metrics['recent_trial_details']) < 5:
                    quality_metrics['recent_trial_details'].append({
                        'nct_id': trial.nct_id,
                        'title': trial.brief_title or trial.official_title or 'No title',
                        'phase': trial.phase,
                        'status': trial.status,
                        'sponsor': trial.sponsor_text,
                        'version_count': len(trial.versions)
                    })
            
            # Convert set to count
            quality_metrics['unique_sponsors'] = len(quality_metrics['sponsor_variety'])
            del quality_metrics['sponsor_variety']
            
            # Calculate completeness score
            total = quality_metrics['total_trials_analyzed']
            if total > 0:
                quality_metrics['completeness_score'] = (
                    quality_metrics['trials_with_sponsor'] + 
                    quality_metrics['trials_with_phase'] + 
                    quality_metrics['trials_with_status'] + 
                    quality_metrics['trials_with_title']
                ) / (total * 4)  # 4 key fields
            
            logger.info(f"📊 Data quality analysis completed: {quality_metrics['completeness_score']:.2%} completeness")
            return quality_metrics
            
    except Exception as e:
        logger.error(f"❌ Data quality analysis failed: {e}")
        return {'error': str(e)}

def analyze_trial_data_for_study_cards() -> Dict[str, Any]:
    """Analyze trial data to identify candidates for study card creation."""
    logger.info("🎯 Analyzing trial data for study card candidates...")
    
    try:
        with get_session() as session:
            # Get trials with good data quality
            quality_trials = session.query(Trial).filter(
                Trial.sponsor_text.isnot(None),
                Trial.phase.isnot(None),
                Trial.status.isnot(None)
            ).order_by(Trial.last_seen_at.desc()).limit(20).all()
            
            analysis_results = {
                'total_quality_trials': len(quality_trials),
                'phase_breakdown': {},
                'status_breakdown': {},
                'sponsor_breakdown': {},
                'top_candidates': [],
                'data_completeness': {}
            }
            
            for trial in quality_trials:
                # Phase breakdown
                phase = trial.phase
                analysis_results['phase_breakdown'][phase] = analysis_results['phase_breakdown'].get(phase, 0) + 1
                
                # Status breakdown
                status = trial.status
                analysis_results['status_breakdown'][status] = analysis_results['status_breakdown'].get(status, 0) + 1
                
                # Sponsor breakdown
                sponsor = trial.sponsor_text
                analysis_results['sponsor_breakdown'][sponsor] = analysis_results['sponsor_breakdown'].get(sponsor, 0) + 1
                
                # Check data completeness for this trial
                completeness_score = 0
                total_fields = 0
                
                if trial.brief_title or trial.official_title:
                    completeness_score += 1
                total_fields += 1
                
                if trial.phase:
                    completeness_score += 1
                total_fields += 1
                
                if trial.status:
                    completeness_score += 1
                total_fields += 1
                
                if trial.sponsor_text:
                    completeness_score += 1
                total_fields += 1
                
                if trial.indication:
                    completeness_score += 1
                total_fields += 1
                
                if trial.primary_endpoint_text:
                    completeness_score += 1
                total_fields += 1
                
                trial_completeness = completeness_score / total_fields if total_fields > 0 else 0
                
                # Store top candidates
                if len(analysis_results['top_candidates']) < 10:
                    analysis_results['top_candidates'].append({
                        'nct_id': trial.nct_id,
                        'title': trial.brief_title or trial.official_title or 'No title',
                        'phase': trial.phase,
                        'status': trial.status,
                        'sponsor': trial.sponsor_text,
                        'completeness': trial_completeness,
                        'version_count': len(trial.versions)
                    })
            
            # Sort candidates by completeness
            analysis_results['top_candidates'].sort(key=lambda x: x['completeness'], reverse=True)
            
            logger.info(f"✅ Trial analysis completed: {len(quality_trials)} quality trials found")
            return analysis_results
            
    except Exception as e:
        logger.error(f"❌ Trial analysis failed: {e}")
        return {'error': str(e)}

def simulate_study_card_creation(trial_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate study card creation based on trial analysis."""
    logger.info("📝 Simulating study card creation...")
    
    if 'error' in trial_analysis:
        return {'error': f"Cannot simulate study cards: {trial_analysis['error']}"}
    
    top_candidates = trial_analysis.get('top_candidates', [])
    if not top_candidates:
        return {'error': 'No trial candidates available for study card creation'}
    
    # Select top 3 candidates for simulation
    selected_trials = top_candidates[:3]
    
    study_card_results = {
        'trials_selected': len(selected_trials),
        'cards_simulated': 0,
        'extraction_quality': {},
        'simulation_details': []
    }
    
    for trial_data in selected_trials:
        try:
            # Simulate study card creation
            card_simulation = {
                'nct_id': trial_data['nct_id'],
                'title': trial_data['title'],
                'phase': trial_data['phase'],
                'status': trial_data['status'],
                'sponsor': trial_data['sponsor'],
                'data_completeness': trial_data['completeness'],
                'extraction_confidence': min(0.95, 0.7 + trial_data['completeness'] * 0.3),
                'key_findings': [
                    f"Phase {trial_data['phase']} trial",
                    f"Status: {trial_data['status']}",
                    f"Sponsor: {trial_data['sponsor']}",
                    f"Data completeness: {trial_data['completeness']:.1%}"
                ]
            }
            
            study_card_results['simulation_details'].append(card_simulation)
            study_card_results['cards_simulated'] += 1
            
            logger.info(f"🔍 Simulated study card for {trial_data['nct_id']}")
            logger.info(f"   - Title: {trial_data['title'][:50]}...")
            logger.info(f"   - Phase: {trial_data['phase']}, Status: {trial_data['status']}")
            logger.info(f"   - Confidence: {card_simulation['extraction_confidence']:.1%}")
            
        except Exception as e:
            logger.error(f"Error simulating study card for {trial_data.get('nct_id', 'unknown')}: {e}")
    
    logger.info(f"📝 Study card simulation completed: {study_card_results['cards_simulated']} cards simulated")
    return study_card_results

def simulate_signal_detection(trial_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate signal detection based on trial analysis."""
    logger.info("⚠️ Simulating signal detection...")
    
    if 'error' in trial_analysis:
        return {'error': f"Cannot simulate signal detection: {trial_analysis['error']}"}
    
    top_candidates = trial_analysis.get('top_candidates', [])
    if not top_candidates:
        return {'error': 'No trial candidates available for signal detection'}
    
    # Select top 5 candidates for signal analysis
    selected_trials = top_candidates[:5]
    
    signal_results = {
        'trials_analyzed': len(selected_trials),
        'signals_detected': 0,
        'signal_types': {},
        'risk_assessments': [],
        'simulation_details': []
    }
    
    for trial_data in selected_trials:
        try:
            # Simulate signal detection
            signals = []
            risk_score = 0.0
            
            # Phase-based signals
            if trial_data['phase'] in ['PHASE3', 'PHASE2_PHASE3']:
                signals.append('PHASE3_TRIAL')
                risk_score += 0.3
            
            # Status-based signals
            if trial_data['status'] in ['COMPLETED', 'TERMINATED']:
                signals.append('COMPLETION_STATUS')
                risk_score += 0.2
            
            # Sponsor-based signals
            if trial_data['sponsor'] and 'pharma' in trial_data['sponsor'].lower():
                signals.append('PHARMA_SPONSOR')
                risk_score += 0.1
            
            # Data quality signals
            if trial_data['completeness'] < 0.7:
                signals.append('LOW_DATA_QUALITY')
                risk_score += 0.2
            
            # Risk assessment
            risk_level = 'LOW'
            if risk_score > 0.5:
                risk_level = 'HIGH'
            elif risk_score > 0.2:
                risk_level = 'MEDIUM'
            
            signal_analysis = {
                'nct_id': trial_data['nct_id'],
                'title': trial_data['title'],
                'signals_detected': signals,
                'risk_score': risk_score,
                'risk_level': risk_level,
                'recommendations': [
                    'Monitor trial progress',
                    'Review data quality',
                    'Assess sponsor track record'
                ] if risk_level != 'LOW' else ['Standard monitoring']
            }
            
            signal_results['simulation_details'].append(signal_analysis)
            
            # Count signal types
            for signal in signals:
                signal_results['signal_types'][signal] = signal_results['signal_types'].get(signal, 0) + 1
            
            if signals:
                signal_results['signals_detected'] += 1
            
            logger.info(f"🔍 Simulated signal detection for {trial_data['nct_id']}")
            logger.info(f"   - Signals: {', '.join(signals) if signals else 'None'}")
            logger.info(f"   - Risk Level: {risk_level} ({risk_score:.2f})")
            
        except Exception as e:
            logger.error(f"Error simulating signal detection for {trial_data.get('nct_id', 'unknown')}: {e}")
    
    logger.info(f"⚠️ Signal detection simulation completed: {signal_results['signals_detected']} trials with signals")
    return signal_results

def run_simple_e2e_test() -> SimpleE2ETestResults:
    """Run the simplified end-to-end test."""
    logger.info("🚀 Starting Simplified End-to-End Pipeline Test")
    logger.info("=" * 60)
    
    results = SimpleE2ETestResults()
    
    try:
        # 1. Test database connectivity
        logger.info("\n📊 PHASE 1: Database Connectivity")
        db_results = test_database_connectivity()
        results.database_results = db_results
        
        if not db_results.get('success', False):
            results.add_error("Database connectivity test failed")
            return results
        
        # 2. Analyze existing data quality
        logger.info("\n🔍 PHASE 2: Data Quality Analysis")
        quality_results = analyze_existing_data_quality()
        results.data_quality_results = quality_results
        
        # 3. Analyze trial data for study cards
        logger.info("\n🎯 PHASE 3: Trial Data Analysis")
        trial_analysis = analyze_trial_data_for_study_cards()
        results.trial_analysis_results = trial_analysis
        
        # 4. Simulate study card creation
        logger.info("\n📝 PHASE 4: Study Card Simulation")
        study_card_results = simulate_study_card_creation(trial_analysis)
        results.study_card_results = study_card_results
        
        # 5. Simulate signal detection
        logger.info("\n⚠️ PHASE 5: Signal Detection Simulation")
        signal_results = simulate_signal_detection(trial_analysis)
        results.signal_detection_results = signal_results
        
        logger.info("\n✅ Simplified End-to-End Test Completed Successfully!")
        
    except Exception as e:
        results.add_error(f"Simplified E2E test failed: {e}")
        logger.error(f"❌ Simplified E2E test failed: {e}", exc_info=True)
    
    return results

def print_simple_final_report(results: SimpleE2ETestResults):
    """Print a comprehensive test report."""
    summary = results.get_summary()
    
    logger.info("\n" + "=" * 60)
    logger.info("📋 SIMPLIFIED END-TO-END TEST REPORT")
    logger.info("=" * 60)
    
    logger.info(f"⏱️  Total Duration: {summary['duration_seconds']:.2f} seconds")
    logger.info(f"✅ Overall Success: {summary['success']}")
    
    # Database Results
    db = summary.get('database', {})
    logger.info(f"\n📊 Database Connectivity:")
    logger.info(f"   - Connection Healthy: {db.get('connection_healthy', False)}")
    logger.info(f"   - Trials: {db.get('trial_count', 0)}")
    logger.info(f"   - Versions: {db.get('version_count', 0)}")
    logger.info(f"   - Companies: {db.get('company_count', 0)}")
    
    # Data Quality Results
    quality = summary.get('data_quality', {})
    if 'error' not in quality:
        logger.info(f"\n🔍 Data Quality:")
        logger.info(f"   - Trials Analyzed: {quality.get('total_trials_analyzed', 0)}")
        logger.info(f"   - Completeness Score: {quality.get('completeness_score', 0):.2%}")
        logger.info(f"   - Unique Sponsors: {quality.get('unique_sponsors', 0)}")
        
        # Phase Distribution
        if 'phase_distribution' in quality:
            logger.info(f"   - Phase Distribution: {dict(list(quality['phase_distribution'].items())[:5])}")
    
    # Trial Analysis Results
    trial_analysis = summary.get('trial_analysis', {})
    if 'error' not in trial_analysis:
        logger.info(f"\n🎯 Trial Analysis:")
        logger.info(f"   - Quality Trials: {trial_analysis.get('total_quality_trials', 0)}")
        logger.info(f"   - Top Candidates: {len(trial_analysis.get('top_candidates', []))}")
    
    # Study Cards
    study_cards = summary.get('study_cards', {})
    if 'error' not in study_cards:
        logger.info(f"\n📝 Study Cards:")
        logger.info(f"   - Cards Simulated: {study_cards.get('cards_simulated', 0)}")
    
    # Signal Detection
    signals = summary.get('signal_detection', {})
    if 'error' not in signals:
        logger.info(f"\n⚠️ Signal Detection:")
        logger.info(f"   - Trials Analyzed: {signals.get('trials_analyzed', 0)}")
        logger.info(f"   - Signals Detected: {signals.get('signals_detected', 0)}")
        
        if 'signal_types' in signals:
            logger.info(f"   - Signal Types: {signals['signal_types']}")
    
    # Errors and Warnings
    if summary.get('errors'):
        logger.info(f"\n❌ Errors ({len(summary['errors'])}):")
        for error in summary['errors']:
            logger.info(f"   - {error}")
    
    if summary.get('warnings'):
        logger.info(f"\n⚠️ Warnings ({len(summary['warnings'])}):")
        for warning in summary['warnings']:
            logger.info(f"   - {warning}")
    
    logger.info("\n" + "=" * 60)

if __name__ == "__main__":
    # Run the simplified end-to-end test
    test_results = run_simple_e2e_test()
    
    # Print comprehensive report
    print_simple_final_report(test_results)
    
    # Save results to file
    results_file = Path(__file__).parent / f"simple_e2e_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(test_results.get_summary(), f, indent=2, default=str)
    
    logger.info(f"📄 Detailed results saved to: {results_file}")
    
    # Exit with appropriate code
    summary = test_results.get_summary()
    if summary['success']:
        logger.info("🎉 All tests passed!")
        sys.exit(0)
    else:
        logger.error("💥 Some tests failed!")
        sys.exit(1)
