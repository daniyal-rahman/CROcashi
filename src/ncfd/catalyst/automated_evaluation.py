"""
Automated Evaluation System with LLM Integration

Integrates the LLM resolution service with existing study card evaluation
to provide comprehensive automated ranking with enhanced 1-100 scoring.

This system provides:
- Automated study card evaluation and ranking
- LLM-based resolution for tie-breaking
- Batch processing capabilities
- Integration with database storage
- Comprehensive reporting and analytics
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import asyncio

from .evaluator import AutomaticStudyCardEvaluator
from .llm_resolution import LLMResolutionService, StudyCardForResolution, resolve_study_card_rankings_sync
from .comprehensive_service import ComprehensiveStudyCardService
from .models import StudyCardRanking, LLMResolutionScore
from .rank import sort_ranked_trials, calculate_ranking_confidence


@dataclass
class AutomatedEvaluationRequest:
    """Request for automated evaluation."""
    study_cards: List[Dict[str, Any]]
    use_llm_resolution: bool = True
    resolution_context: Optional[str] = None
    ranking_criteria: Optional[List[str]] = None
    batch_size: int = 10
    save_to_database: bool = True


@dataclass
class AutomatedEvaluationResult:
    """Result of automated evaluation."""
    study_id: int
    trial_id: int
    base_quality_score: float
    base_quality_rank: int
    base_confidence: float
    llm_enhanced_score: Optional[int]
    llm_confidence: Optional[float]
    llm_reasoning: Optional[str]
    final_ranking_position: int
    ranking_factors: List[str]
    evaluation_timestamp: datetime
    processing_time: float


@dataclass
class BatchEvaluationResult:
    """Result of batch automated evaluation."""
    evaluated_cards: List[AutomatedEvaluationResult]
    llm_resolution_summary: Optional[str]
    total_processing_time: float
    average_confidence: float
    ranking_distribution: Dict[str, int]
    high_risk_studies: List[AutomatedEvaluationResult]
    evaluation_summary: str


class AutomatedEvaluationSystem:
    """Automated evaluation system with LLM integration."""
    
    def __init__(self):
        self.evaluator = AutomaticStudyCardEvaluator()
        self.llm_service = LLMResolutionService()
        self.comprehensive_service = ComprehensiveStudyCardService()
        
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Default ranking criteria for LLM resolution
        self.default_ranking_criteria = [
            "study design quality and robustness",
            "statistical power and sample size adequacy",
            "endpoint definition clarity and clinical relevance",
            "data quality and completeness",
            "publication quality and journal impact",
            "conflict of interest transparency",
            "protocol adherence and amendments",
            "subgroup analysis quality",
            "safety data comprehensiveness",
            "regulatory compliance and pathway clarity"
        ]
    
    async def evaluate_study_cards_automated(self, 
                                          request: AutomatedEvaluationRequest) -> BatchEvaluationResult:
        """Perform automated evaluation of study cards with optional LLM resolution."""
        
        start_time = datetime.now()
        
        if not request.study_cards:
            raise ValueError("No study cards provided for evaluation")
        
        self.logger.info(f"Starting automated evaluation of {len(request.study_cards)} study cards")
        
        # Step 1: Perform basic evaluation
        basic_results = await self._perform_basic_evaluation(request.study_cards)
        
        # Step 2: Group study cards by base rank for LLM resolution
        grouped_cards = self._group_cards_by_base_rank(basic_results)
        
        # Step 3: Perform LLM resolution if requested
        llm_results = {}
        llm_resolution_summary = None
        
        if request.use_llm_resolution:
            llm_results, llm_resolution_summary = await self._perform_llm_resolution(
                grouped_cards, request
            )
        
        # Step 4: Integrate results and create final rankings
        final_results = self._integrate_evaluation_results(
            basic_results, llm_results, request.use_llm_resolution
        )
        
        # Step 5: Sort and assign final ranking positions
        sorted_results = self._assign_final_rankings(final_results)
        
        # Step 6: Generate evaluation summary
        evaluation_summary = self._generate_evaluation_summary(sorted_results, request)
        
        # Step 7: Identify high-risk studies
        high_risk_studies = self._identify_high_risk_studies(sorted_results)
        
        # Calculate processing time
        total_processing_time = (datetime.now() - start_time).total_seconds()
        
        # Calculate average confidence
        total_confidence = sum(result.base_confidence for result in sorted_results)
        if llm_results:
            total_confidence += sum(
                result.llm_confidence for result in sorted_results 
                if result.llm_confidence is not None
            )
        average_confidence = total_confidence / (len(sorted_results) * (2 if llm_results else 1))
        
        # Generate ranking distribution
        ranking_distribution = self._calculate_ranking_distribution(sorted_results)
        
        return BatchEvaluationResult(
            evaluated_cards=sorted_results,
            llm_resolution_summary=llm_resolution_summary,
            total_processing_time=total_processing_time,
            average_confidence=average_confidence,
            ranking_distribution=ranking_distribution,
            high_risk_studies=high_risk_studies,
            evaluation_summary=evaluation_summary
        )
    
    async def _perform_basic_evaluation(self, 
                                      study_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Perform basic evaluation of study cards."""
        
        basic_results = []
        
        for card_data in study_cards:
            try:
                study_id = card_data.get('study_id', 1)
                trial_id = card_data.get('trial_id', 1)
                extracted_jsonb = card_data.get('extracted_jsonb', {})
                
                # Perform automatic evaluation
                evaluation = self.evaluator.evaluate_study_card(
                    study_id, trial_id, extracted_jsonb
                )
                
                # Store basic evaluation results
                basic_result = {
                    'study_id': study_id,
                    'trial_id': trial_id,
                    'extracted_jsonb': extracted_jsonb,
                    'quality_score': evaluation.quality_score,
                    'quality_rank': evaluation.quality_rank,
                    'confidence': evaluation.confidence_score,
                    'evaluation_notes': evaluation.evaluation_notes,
                    'risk_factors': evaluation.risk_factors
                }
                
                basic_results.append(basic_result)
                
            except Exception as e:
                self.logger.error(f"Error evaluating study card {card_data.get('study_id', 'unknown')}: {e}")
                continue
        
        return basic_results
    
    def _group_cards_by_base_rank(self, 
                                 basic_results: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
        """Group study cards by their base quality rank."""
        
        grouped_cards = {}
        
        for result in basic_results:
            base_rank = result['quality_rank']
            if base_rank not in grouped_cards:
                grouped_cards[base_rank] = []
            grouped_cards[base_rank].append(result)
        
        return grouped_cards
    
    async def _perform_llm_resolution(self, 
                                    grouped_cards: Dict[int, List[Dict[str, Any]]],
                                    request: AutomatedEvaluationRequest) -> Tuple[Dict[int, List[Any]], Optional[str]]:
        """Perform LLM resolution for study cards with the same base rank."""
        
        llm_results = {}
        all_resolution_summaries = []
        
        for base_rank, cards in grouped_cards.items():
            # Only perform LLM resolution if there are multiple cards with the same rank
            if len(cards) > 1:
                try:
                    self.logger.info(f"Performing LLM resolution for {len(cards)} cards with base rank {base_rank}")
                    
                    # Prepare cards for LLM resolution
                    prepared_cards = self.llm_service.prepare_study_cards_for_resolution(cards)
                    
                    # Perform LLM resolution
                    resolution_result = await self.llm_service.resolve_study_card_rankings(
                        prepared_cards,
                        request.resolution_context,
                        request.ranking_criteria or self.default_ranking_criteria
                    )
                    
                    # Store results
                    llm_results[base_rank] = resolution_result.resolved_cards
                    all_resolution_summaries.append(resolution_result.resolution_summary)
                    
                except Exception as e:
                    self.logger.error(f"Error in LLM resolution for rank {base_rank}: {e}")
                    # Continue with other ranks
                    continue
        
        # Combine all resolution summaries
        llm_resolution_summary = "\n\n".join(all_resolution_summaries) if all_resolution_summaries else None
        
        return llm_results, llm_resolution_summary
    
    def _integrate_evaluation_results(self, 
                                    basic_results: List[Dict[str, Any]],
                                    llm_results: Dict[int, List[Any]],
                                    use_llm_resolution: bool) -> List[AutomatedEvaluationResult]:
        """Integrate basic evaluation results with LLM resolution results."""
        
        integrated_results = []
        
        for basic_result in basic_results:
            study_id = basic_result['study_id']
            trial_id = basic_result['trial_id']
            base_rank = basic_result['quality_rank']
            
            # Initialize LLM-related fields
            llm_enhanced_score = None
            llm_confidence = None
            llm_reasoning = None
            
            # Get LLM resolution results if available
            if use_llm_resolution and base_rank in llm_results:
                llm_result = next(
                    (r for r in llm_results[base_rank] 
                     if r.study_id == study_id and r.trial_id == trial_id),
                    None
                )
                
                if llm_result:
                    llm_enhanced_score = llm_result.enhanced_score_1_100
                    llm_confidence = llm_result.confidence
                    llm_reasoning = llm_result.resolution_reasoning
            
            # Create integrated result
            integrated_result = AutomatedEvaluationResult(
                study_id=study_id,
                trial_id=trial_id,
                base_quality_score=basic_result['quality_score'],
                base_quality_rank=base_rank,
                base_confidence=basic_result['confidence'],
                llm_enhanced_score=llm_enhanced_score,
                llm_confidence=llm_confidence,
                llm_reasoning=llm_reasoning,
                final_ranking_position=0,  # Will be set later
                ranking_factors=basic_result.get('risk_factors', []),
                evaluation_timestamp=datetime.now(),
                processing_time=0.0  # Will be calculated later
            )
            
            integrated_results.append(integrated_result)
        
        return integrated_results
    
    def _assign_final_rankings(self, 
                              integrated_results: List[AutomatedEvaluationResult]) -> List[AutomatedEvaluationResult]:
        """Assign final ranking positions based on integrated results."""
        
        # Sort by base rank first, then by LLM enhanced score if available
        sorted_results = sorted(
            integrated_results,
            key=lambda x: (
                x.base_quality_rank,
                -(x.llm_enhanced_score or 0),  # Higher LLM score = better rank
                -x.base_quality_score  # Higher quality score = better rank
            )
        )
        
        # Assign final ranking positions
        for i, result in enumerate(sorted_results):
            result.final_ranking_position = i + 1
        
        return sorted_results
    
    def _generate_evaluation_summary(self, 
                                   sorted_results: List[AutomatedEvaluationResult],
                                   request: AutomatedEvaluationRequest) -> str:
        """Generate comprehensive evaluation summary."""
        
        if not sorted_results:
            return "No study cards were evaluated."
        
        # Calculate statistics
        total_cards = len(sorted_results)
        base_ranks = {}
        llm_resolved = sum(1 for r in sorted_results if r.llm_enhanced_score is not None)
        
        for result in sorted_results:
            base_rank = result.base_quality_rank
            if base_rank not in base_ranks:
                base_ranks[base_rank] = 0
            base_ranks[base_rank] += 1
        
        summary = f"""
Automated Evaluation Summary:
- Total study cards evaluated: {total_cards}
- LLM resolution applied: {request.use_llm_resolution}
- Cards with LLM resolution: {llm_resolved}
- Base rank distribution:
"""
        
        for rank in sorted(base_ranks.keys()):
            count = base_ranks[rank]
            percentage = (count / total_cards) * 100
            summary += f"  Rank {rank}: {count} cards ({percentage:.1f}%)\n"
        
        # Add top and bottom performers
        if sorted_results:
            top_performer = sorted_results[0]
            bottom_performer = sorted_results[-1]
            
            summary += f"""
Top Performer:
- Study ID: {top_performer.study_id}, Trial ID: {top_performer.trial_id}
- Base Rank: {top_performer.base_quality_rank}
- LLM Enhanced Score: {top_performer.llm_enhanced_score or 'N/A'}
- Final Position: {top_performer.final_ranking_position}

Bottom Performer:
- Study ID: {bottom_performer.study_id}, Trial ID: {bottom_performer.trial_id}
- Base Rank: {bottom_performer.base_quality_rank}
- LLM Enhanced Score: {bottom_performer.llm_enhanced_score or 'N/A'}
- Final Position: {bottom_performer.final_ranking_position}
"""
        
        return summary.strip()
    
    def _identify_high_risk_studies(self, 
                                   sorted_results: List[AutomatedEvaluationResult]) -> List[AutomatedEvaluationResult]:
        """Identify high-risk studies based on ranking and quality metrics."""
        
        high_risk_studies = []
        
        for result in sorted_results:
            # High risk criteria
            is_high_risk = False
            
            # Check base rank (7-10 indicates high risk)
            if result.base_quality_rank >= 7:
                is_high_risk = True
            
            # Check if in bottom 20% of final rankings
            if result.final_ranking_position > len(sorted_results) * 0.8:
                is_high_risk = True
            
            # Check base confidence (low confidence = higher risk)
            if result.base_confidence < 0.3:
                is_high_risk = True
            
            if is_high_risk:
                high_risk_studies.append(result)
        
        return high_risk_studies
    
    def _calculate_ranking_distribution(self, 
                                      sorted_results: List[AutomatedEvaluationResult]) -> Dict[str, int]:
        """Calculate distribution of rankings across different categories."""
        
        distribution = {
            'excellent': 0,    # Rank 1-2
            'good': 0,         # Rank 3-4
            'fair': 0,         # Rank 5-6
            'poor': 0,         # Rank 7-8
            'very_poor': 0     # Rank 9-10
        }
        
        for result in sorted_results:
            base_rank = result.base_quality_rank
            
            if base_rank <= 2:
                distribution['excellent'] += 1
            elif base_rank <= 4:
                distribution['good'] += 1
            elif base_rank <= 6:
                distribution['fair'] += 1
            elif base_rank <= 8:
                distribution['poor'] += 1
            else:
                distribution['very_poor'] += 1
        
        return distribution
    
    def save_evaluation_results(self, 
                              results: List[AutomatedEvaluationResult],
                              db_session) -> None:
        """Save automated evaluation results to the database."""
        
        try:
            for result in results:
                # Create or update StudyCardRanking
                study_card_ranking = StudyCardRanking(
                    trial_id=result.trial_id,
                    evaluator_id='automated_system',
                    score_1_10=result.base_quality_rank,
                    score_1_100=result.llm_enhanced_score,
                    confidence=result.base_confidence,
                    notes=result.llm_reasoning or "Automated evaluation",
                    created_at=result.evaluation_timestamp
                )
                
                db_session.add(study_card_ranking)
                
                # Create LLMResolutionScore if available
                if result.llm_enhanced_score is not None:
                    llm_score = LLMResolutionScore(
                        trial_id=result.trial_id,
                        base_score_1_10=result.base_quality_rank,
                        enhanced_score_1_100=result.llm_enhanced_score,
                        resolution_reasoning=result.llm_reasoning or "Automated LLM resolution",
                        confidence=result.llm_confidence or 0.5,
                        ranking_factors=result.ranking_factors,
                        relative_position=result.final_ranking_position,
                        model_used=self.llm_service.model,
                        timestamp=result.evaluation_timestamp
                    )
                    
                    db_session.add(llm_score)
            
            db_session.commit()
            self.logger.info(f"Saved {len(results)} automated evaluation results to database")
            
        except Exception as e:
            self.logger.error(f"Error saving evaluation results: {e}")
            db_session.rollback()
            raise
    
    def generate_evaluation_report(self, 
                                 batch_result: BatchEvaluationResult,
                                 include_details: bool = False) -> str:
        """Generate a comprehensive evaluation report."""
        
        report = f"""
AUTOMATED EVALUATION REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'=' * 50}

{batch_result.evaluation_summary}

LLM Resolution Summary:
{batch_result.llm_resolution_summary or 'No LLM resolution performed'}

Performance Metrics:
- Total Processing Time: {batch_result.total_processing_time:.2f} seconds
- Average Confidence: {batch_result.average_confidence:.2f}
- High-Risk Studies: {len(batch_result.high_risk_studies)}

Ranking Distribution:
"""
        
        for category, count in batch_result.ranking_distribution.items():
            percentage = (count / len(batch_result.evaluated_cards)) * 100
            report += f"- {category.replace('_', ' ').title()}: {count} ({percentage:.1f}%)\n"
        
        if include_details:
            report += "\nDetailed Results:\n"
            for result in batch_result.evaluated_cards:
                report += f"""
Study {result.study_id} (Trial {result.trial_id}):
- Base Rank: {result.base_quality_rank}
- LLM Enhanced Score: {result.llm_enhanced_score or 'N/A'}
- Final Position: {result.final_ranking_position}
- Base Confidence: {result.base_confidence:.2f}
- LLM Confidence: {result.llm_confidence or 'N/A'}
"""
        
        return report.strip()


# Convenience function for synchronous usage
def evaluate_study_cards_automated_sync(request: AutomatedEvaluationRequest) -> BatchEvaluationResult:
    """Synchronous wrapper for evaluate_study_cards_automated."""
    
    system = AutomatedEvaluationSystem()
    return asyncio.run(system.evaluate_study_cards_automated(request))
