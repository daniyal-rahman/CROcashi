"""
Comprehensive Study Card Service

Integrates all enhanced field extractors and analyzers to provide:
- Complete field extraction and validation
- Tone analysis and claim strength assessment
- Conflicts of interest and funding analysis
- Publication details and registry discrepancy detection
- Data location mapping with tables, figures, and quote spans
- Comprehensive reviewer notes with limitations, oddities, and quality assessment
- Enhanced study card quality scoring and ranking
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import json
from datetime import datetime

from .enhanced_extractor import (
    EnhancedStudyCardExtractor, ToneAnalysisResult, ConflictsFundingResult,
    PublicationDetailsResult, DataLocationResult
)
from .reviewer_analyzer import (
    ReviewerNotesAnalyzer, ReviewerNotesResult, Limitation, Oddity,
    GeographicOutlier, Discrepancy, QualityAssessment
)
from .evaluator import AutomaticStudyCardEvaluator
from .quality import StudyCardQualityAnalyzer
from .extractor import StudyCardFieldExtractor
from .validation import StudyCardFieldValidator
from .service import StudyCardQualityService


@dataclass
class ComprehensiveAnalysisResult:
    """Complete comprehensive analysis result."""
    # Basic analysis
    basic_fields: Dict[str, Any]
    quality_score: float
    quality_rank: int
    quality_confidence: float
    
    # Enhanced analysis
    tone_analysis: ToneAnalysisResult
    conflicts_funding: ConflictsFundingResult
    publication_details: PublicationDetailsResult
    data_location: DataLocationResult
    
    # Reviewer analysis
    reviewer_notes: ReviewerNotesResult
    
    # Overall assessment
    overall_quality: str
    evidence_strength: str
    data_completeness: float
    total_issues: int
    critical_issues: int
    major_issues: int
    
    # Metadata
    analysis_timestamp: datetime
    analysis_version: str
    confidence: float


class ComprehensiveStudyCardService:
    """Comprehensive service for complete study card analysis."""
    
    def __init__(self):
        self.enhanced_extractor = EnhancedStudyCardExtractor()
        self.reviewer_analyzer = ReviewerNotesAnalyzer()
        self.automatic_evaluator = AutomaticStudyCardEvaluator()
        self.quality_service = StudyCardQualityService()
        self.analysis_version = "2.0.0"
    
    def analyze_study_card_comprehensive(self, study_id: int, trial_id: int, 
                                       study_data: Dict[str, Any]) -> ComprehensiveAnalysisResult:
        """Perform comprehensive analysis of a study card."""
        
        # Perform basic quality analysis
        basic_quality = self.automatic_evaluator.evaluate_study_card(
            study_id, trial_id, study_data
        )
        
        # Extract enhanced fields
        enhanced_fields = self.enhanced_extractor.extract_enhanced_fields(study_data)
        
        # Generate reviewer notes
        reviewer_notes = self.reviewer_analyzer.analyze_reviewer_notes(study_data)
        
        # Compile comprehensive result
        result = self._compile_comprehensive_result(
            basic_quality, enhanced_fields, reviewer_notes, study_data
        )
        
        return result
    
    def bulk_analyze_study_cards(self, study_data_list: List[Tuple[int, int, Dict[str, Any]]]) -> List[ComprehensiveAnalysisResult]:
        """Perform comprehensive analysis on multiple study cards."""
        results = []
        
        for study_id, trial_id, study_data in study_data_list:
            try:
                result = self.analyze_study_card_comprehensive(study_id, trial_id, study_data)
                results.append(result)
            except Exception as e:
                # Log error and continue with next study
                print(f"Error analyzing study {study_id}: {e}")
                continue
        
        return results
    
    def get_analysis_summary(self, results: List[ComprehensiveAnalysisResult]) -> Dict[str, Any]:
        """Generate summary statistics from comprehensive analysis results."""
        if not results:
            return {}
        
        summary = {
            'total_studies': len(results),
            'quality_distribution': {},
            'evidence_strength_distribution': {},
            'tone_distribution': {},
            'journal_type_distribution': {},
            'average_data_completeness': 0.0,
            'total_issues': 0,
            'critical_issues': 0,
            'major_issues': 0,
            'limitation_types': {},
            'oddity_types': {},
            'discrepancy_types': {}
        }
        
        # Calculate distributions and averages
        total_completeness = 0.0
        total_issues = 0
        total_critical = 0
        total_major = 0
        
        for result in results:
            # Quality distribution
            quality = result.overall_quality
            summary['quality_distribution'][quality] = summary['quality_distribution'].get(quality, 0) + 1
            
            # Evidence strength distribution
            evidence = result.evidence_strength
            summary['evidence_strength_distribution'][evidence] = summary['evidence_strength_distribution'].get(evidence, 0) + 1
            
            # Tone distribution
            tone = result.tone_analysis.overall_tone.value
            summary['tone_distribution'][tone] = summary['tone_distribution'].get(tone, 0) + 1
            
            # Journal type distribution
            journal_type = result.publication_details.journal_type.value
            summary['journal_type_distribution'][journal_type] = summary['journal_type_distribution'].get(journal_type, 0) + 1
            
            # Data completeness
            total_completeness += result.data_completeness
            
            # Issues
            total_issues += result.total_issues
            total_critical += result.critical_issues
            total_major += result.major_issues
            
            # Limitation types
            for limitation in result.reviewer_notes.limitations:
                lim_type = limitation.type.value
                summary['limitation_types'][lim_type] = summary['limitation_types'].get(lim_type, 0) + 1
            
            # Oddity types
            for oddity in result.reviewer_notes.oddities:
                odd_type = oddity.type.value
                summary['oddity_types'][odd_type] = summary['oddity_types'].get(odd_type, 0) + 1
            
            # Discrepancy types
            for discrepancy in result.reviewer_notes.unexplained_discrepancies:
                disc_type = discrepancy.type.value
                summary['discrepancy_types'][disc_type] = summary['discrepancy_types'].get(disc_type, 0) + 1
        
        # Calculate averages
        summary['average_data_completeness'] = total_completeness / len(results)
        summary['total_issues'] = total_issues
        summary['critical_issues'] = total_critical
        summary['major_issues'] = total_major
        
        return summary
    
    def get_high_risk_studies(self, results: List[ComprehensiveAnalysisResult], 
                             risk_threshold: int = 7) -> List[ComprehensiveAnalysisResult]:
        """Identify high-risk studies based on quality rank and issues."""
        high_risk = []
        
        for result in results:
            # Check quality rank
            if result.quality_rank >= risk_threshold:
                high_risk.append(result)
                continue
            
            # Check for critical issues
            if result.critical_issues > 0:
                high_risk.append(result)
                continue
            
            # Check for major issues
            if result.major_issues >= 3:
                high_risk.append(result)
                continue
            
            # Check evidence strength
            if result.evidence_strength in ['weak', 'insufficient']:
                high_risk.append(result)
                continue
        
        return high_risk
    
    def get_publication_quality_report(self, results: List[ComprehensiveAnalysisResult]) -> Dict[str, Any]:
        """Generate publication quality report."""
        report = {
            'journal_quality': {},
            'open_access_distribution': {},
            'peer_review_distribution': {},
            'impact_factor_ranges': {},
            'registry_discrepancies': 0,
            'publication_issues': []
        }
        
        for result in results:
            pub_details = result.publication_details
            
            # Journal quality by type
            journal_type = pub_details.journal_type.value
            if journal_type not in report['journal_quality']:
                report['journal_quality'][journal_type] = {
                    'count': 0,
                    'avg_impact_factor': 0.0,
                    'open_access_count': 0,
                    'peer_reviewed_count': 0
                }
            
            journal_stats = report['journal_quality'][journal_type]
            journal_stats['count'] += 1
            
            # Impact factor
            if pub_details.impact_factor:
                journal_stats['avg_impact_factor'] += pub_details.impact_factor
            
            # Open access
            if pub_details.open_access:
                journal_stats['open_access_count'] += 1
            
            # Peer reviewed
            if pub_details.peer_reviewed:
                journal_stats['peer_reviewed_count'] += 1
            
            # Open access distribution
            oa_status = str(pub_details.open_access) if pub_details.open_access is not None else 'unknown'
            report['open_access_distribution'][oa_status] = report['open_access_distribution'].get(oa_status, 0) + 1
            
            # Peer review distribution
            pr_status = str(pub_details.peer_reviewed) if pub_details.peer_reviewed is not None else 'unknown'
            report['peer_review_distribution'][pr_status] = report['peer_review_distribution'].get(pr_status, 0) + 1
            
            # Impact factor ranges
            if pub_details.impact_factor:
                if pub_details.impact_factor < 2.0:
                    range_key = '< 2.0'
                elif pub_details.impact_factor < 5.0:
                    range_key = '2.0 - 4.9'
                elif pub_details.impact_factor < 10.0:
                    range_key = '5.0 - 9.9'
                else:
                    range_key = '≥ 10.0'
                
                report['impact_factor_ranges'][range_key] = report['impact_factor_ranges'].get(range_key, 0) + 1
            
            # Registry discrepancies
            if pub_details.registry_discrepancies:
                report['registry_discrepancies'] += len(pub_details.registry_discrepancies)
        
        # Calculate averages for impact factors
        for journal_type, stats in report['journal_quality'].items():
            if stats['count'] > 0:
                stats['avg_impact_factor'] = stats['avg_impact_factor'] / stats['count']
        
        return report
    
    def get_tone_analysis_report(self, results: List[ComprehensiveAnalysisResult]) -> Dict[str, Any]:
        """Generate tone analysis report."""
        report = {
            'overall_tone_distribution': {},
            'claim_strength_distribution': {},
            'cautious_language_examples': [],
            'definitive_language_examples': [],
            'tone_confidence_stats': {
                'min': 1.0,
                'max': 0.0,
                'avg': 0.0
            }
        }
        
        total_confidence = 0.0
        
        for result in results:
            tone_analysis = result.tone_analysis
            
            # Overall tone distribution
            overall_tone = tone_analysis.overall_tone.value
            report['overall_tone_distribution'][overall_tone] = report['overall_tone_distribution'].get(overall_tone, 0) + 1
            
            # Claim strength distribution
            for endpoint, strength in tone_analysis.claim_strength.items():
                if endpoint not in report['claim_strength_distribution']:
                    report['claim_strength_distribution'][endpoint] = {}
                
                strength_value = strength.value
                report['claim_strength_distribution'][endpoint][strength_value] = \
                    report['claim_strength_distribution'][endpoint].get(strength_value, 0) + 1
            
            # Language examples (collect top examples)
            report['cautious_language_examples'].extend(tone_analysis.cautious_language[:3])
            report['definitive_language_examples'].extend(tone_analysis.definitive_language[:3])
            
            # Confidence statistics
            confidence = tone_analysis.confidence
            total_confidence += confidence
            report['tone_confidence_stats']['min'] = min(report['tone_confidence_stats']['min'], confidence)
            report['tone_confidence_stats']['max'] = max(report['tone_confidence_stats']['max'], confidence)
        
        # Calculate average confidence
        if results:
            report['tone_confidence_stats']['avg'] = total_confidence / len(results)
        
        # Limit examples to top 10
        report['cautious_language_examples'] = report['cautious_language_examples'][:10]
        report['definitive_language_examples'] = report['definitive_language_examples'][:10]
        
        return report
    
    def get_conflicts_funding_report(self, results: List[ComprehensiveAnalysisResult]) -> Dict[str, Any]:
        """Generate conflicts and funding report."""
        report = {
            'conflict_types': {},
            'funding_sources': {},
            'sponsor_roles': {},
            'high_conflict_studies': [],
            'funding_transparency': {
                'fully_disclosed': 0,
                'partially_disclosed': 0,
                'not_disclosed': 0
            }
        }
        
        for result in results:
            conflicts_funding = result.conflicts_funding
            
            # Conflict types
            for conflict in conflicts_funding.conflicts_of_interest:
                conflict_type = conflict['type']
                report['conflict_types'][conflict_type] = report['conflict_types'].get(conflict_type, 0) + 1
            
            # Funding sources
            for funding in conflicts_funding.funding_sources:
                funding_type = funding['type']
                report['funding_sources'][funding_type] = report['funding_sources'].get(funding_type, 0) + 1
            
            # Sponsor roles
            for role, value in conflicts_funding.sponsor_role.items():
                if role not in report['sponsor_roles']:
                    report['sponsor_roles'][role] = {'yes': 0, 'no': 0, 'unknown': 0}
                
                if value is True:
                    report['sponsor_roles'][role]['yes'] += 1
                elif value is False:
                    report['sponsor_roles'][role]['no'] += 1
                else:
                    report['sponsor_roles'][role]['unknown'] += 1
            
            # High conflict studies
            if len(conflicts_funding.conflicts_of_interest) >= 3:
                report['high_conflict_studies'].append({
                    'study_id': result.basic_fields.get('study_id', 'Unknown'),
                    'conflicts_count': len(conflicts_funding.conflicts_of_interest),
                    'conflicts': conflicts_funding.conflicts_of_interest
                })
            
            # Funding transparency
            if conflicts_funding.funding_sources:
                if len(conflicts_funding.funding_sources) >= 2:
                    report['funding_transparency']['fully_disclosed'] += 1
                else:
                    report['funding_transparency']['partially_disclosed'] += 1
            else:
                report['funding_transparency']['not_disclosed'] += 1
        
        return report
    
    def export_analysis_to_json(self, result: ComprehensiveAnalysisResult) -> str:
        """Export analysis result to JSON format."""
        # Convert dataclass to dict for JSON serialization
        result_dict = {
            'basic_fields': result.basic_fields,
            'quality_score': result.quality_score,
            'quality_rank': result.quality_rank,
            'quality_confidence': result.quality_confidence,
            'tone_analysis': {
                'overall_tone': result.tone_analysis.overall_tone.value,
                'claim_strength': {k: v.value for k, v in result.tone_analysis.claim_strength.items()},
                'cautious_language': result.tone_analysis.cautious_language,
                'definitive_language': result.tone_analysis.definitive_language,
                'confidence': result.tone_analysis.confidence
            },
            'conflicts_funding': {
                'conflicts_of_interest': result.conflicts_funding.conflicts_of_interest,
                'funding_sources': result.conflicts_funding.funding_sources,
                'sponsor_role': result.conflicts_funding.sponsor_role,
                'confidence': result.conflicts_funding.confidence
            },
            'publication_details': {
                'journal_type': result.publication_details.journal_type.value,
                'journal_name': result.publication_details.journal_name,
                'impact_factor': result.publication_details.impact_factor,
                'open_access': result.publication_details.open_access,
                'peer_reviewed': result.publication_details.peer_reviewed,
                'publication_date': result.publication_details.publication_date,
                'doi': result.publication_details.doi,
                'pmid': result.publication_details.pmid,
                'registry_discrepancies': result.publication_details.registry_discrepancies,
                'confidence': result.publication_details.confidence
            },
            'data_location': {
                'tables': result.data_location.tables,
                'figures': result.data_location.figures,
                'quote_spans': result.data_location.quote_spans,
                'confidence': result.data_location.confidence
            },
            'reviewer_notes': {
                'limitations': [
                    {
                        'type': l.type.value,
                        'description': l.description,
                        'severity': l.severity.value,
                        'evidence': l.evidence
                    } for l in result.reviewer_notes.limitations
                ],
                'oddities': [
                    {
                        'type': o.type.value,
                        'description': o.description,
                        'evidence': o.evidence
                    } for o in result.reviewer_notes.oddities
                ],
                'geographic_outliers': [
                    {
                        'regions': g.regions,
                        'description': g.description,
                        'impact': g.impact.value,
                        'evidence': g.evidence
                    } for g in result.reviewer_notes.geographic_outliers
                ],
                'unexplained_discrepancies': [
                    {
                        'type': d.type.value,
                        'description': d.description,
                        'source1': d.source1,
                        'source2': d.source2,
                        'evidence': d.evidence
                    } for d in result.reviewer_notes.unexplained_discrepancies
                ],
                'quality_assessment': {
                    'overall_quality': result.reviewer_notes.quality_assessment.overall_quality.value,
                    'data_completeness': result.reviewer_notes.quality_assessment.data_completeness,
                    'evidence_strength': result.reviewer_notes.quality_assessment.evidence_strength.value,
                    'reviewer_confidence': result.reviewer_notes.quality_assessment.reviewer_confidence
                }
            },
            'overall_quality': result.overall_quality,
            'evidence_strength': result.evidence_strength,
            'data_completeness': result.data_completeness,
            'total_issues': result.total_issues,
            'critical_issues': result.critical_issues,
            'major_issues': result.major_issues,
            'analysis_timestamp': result.analysis_timestamp.isoformat(),
            'analysis_version': result.analysis_version,
            'confidence': result.confidence
        }
        
        return json.dumps(result_dict, indent=2, default=str)
    
    def _compile_comprehensive_result(self, basic_quality: Any, enhanced_fields: Dict[str, Any], 
                                    reviewer_notes: ReviewerNotesResult, 
                                    study_data: Dict[str, Any]) -> ComprehensiveAnalysisResult:
        """Compile comprehensive analysis result from all components."""
        
        # Extract basic quality metrics
        quality_score = getattr(basic_quality, 'quality_score', 0.0)
        quality_rank = getattr(basic_quality, 'quality_rank', 0)
        quality_confidence = getattr(basic_quality, 'confidence', 0.0)
        
        # Extract enhanced field results
        tone_analysis = enhanced_fields.get('tone_analysis')
        conflicts_funding = enhanced_fields.get('conflicts_funding')
        publication_details = enhanced_fields.get('publication_details')
        data_location = enhanced_fields.get('data_location')
        
        # Calculate overall metrics
        total_issues = len(reviewer_notes.limitations) + len(reviewer_notes.oddities) + \
                      len(reviewer_notes.unexplained_discrepancies)
        
        critical_issues = sum(1 for l in reviewer_notes.limitations 
                            if l.severity.value == 'critical')
        major_issues = sum(1 for l in reviewer_notes.limitations 
                          if l.severity.value == 'major')
        
        # Determine overall quality and evidence strength
        overall_quality = reviewer_notes.quality_assessment.overall_quality.value
        evidence_strength = reviewer_notes.quality_assessment.evidence_strength.value
        data_completeness = reviewer_notes.quality_assessment.data_completeness
        
        # Calculate overall confidence
        confidence = (quality_confidence + tone_analysis.confidence + 
                     conflicts_funding.confidence + publication_details.confidence + 
                     data_location.confidence + reviewer_notes.confidence) / 6
        
        return ComprehensiveAnalysisResult(
            basic_fields=enhanced_fields.get('basic_fields', {}),
            quality_score=quality_score,
            quality_rank=quality_rank,
            quality_confidence=quality_confidence,
            tone_analysis=tone_analysis,
            conflicts_funding=conflicts_funding,
            publication_details=publication_details,
            data_location=data_location,
            reviewer_notes=reviewer_notes,
            overall_quality=overall_quality,
            evidence_strength=evidence_strength,
            data_completeness=data_completeness,
            total_issues=total_issues,
            critical_issues=critical_issues,
            major_issues=major_issues,
            analysis_timestamp=datetime.now(),
            analysis_version=self.analysis_version,
            confidence=confidence
        )
