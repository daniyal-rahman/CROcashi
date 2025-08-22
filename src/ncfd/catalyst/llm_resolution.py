"""
LLM Resolution Service for Enhanced Study Card Ranking

Uses OpenAI GPT-5 to expand the 1-10 study card ranking scale to 1-100
for relative rankings when multiple study cards have the same 1-10 score.

This service provides:
- Enhanced scoring (1-100) for study cards with the same base rank
- Relative ranking based on comprehensive analysis
- Confidence scoring for LLM-based decisions
- Batch processing for multiple study cards
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import asyncio
from openai import OpenAI
from openai.types.chat import ChatCompletion

from .models import StudyCardRanking, LLMResolutionScore
from .enhanced_extractor import EnhancedStudyCardExtractor
from .reviewer_analyzer import ReviewerNotesAnalyzer


@dataclass
class StudyCardForResolution:
    """Study card data prepared for LLM resolution."""
    study_id: int
    trial_id: int
    base_score_1_10: int
    extracted_jsonb: Dict[str, Any]
    tone_analysis: Dict[str, Any]
    conflicts_funding: Dict[str, Any]
    publication_details: Dict[str, Any]
    data_location: Dict[str, Any]
    reviewer_notes: Dict[str, Any]
    quality_score: float
    quality_confidence: float


@dataclass
class LLMResolutionRequest:
    """Request for LLM resolution of multiple study cards."""
    study_cards: List[StudyCardForResolution]
    resolution_context: str
    ranking_criteria: List[str]
    model: str = "gpt-5-mini"
    temperature: float = 0.1


@dataclass
class LLMResolutionResult:
    """Result of LLM resolution for a study card."""
    study_id: int
    trial_id: int
    base_score_1_10: int
    enhanced_score_1_100: int
    resolution_reasoning: str
    confidence: float
    ranking_factors: List[str]
    relative_position: int
    timestamp: datetime


@dataclass
class BatchResolutionResult:
    """Result of batch LLM resolution."""
    resolved_cards: List[LLMResolutionResult]
    resolution_summary: str
    total_confidence: float
    processing_time: float
    model_used: str


class LLMResolutionService:
    """Service for LLM-based resolution of study card rankings."""
    
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = os.getenv('OPENAI_MODEL_RESOLVER', 'gpt-5-mini')
        self.enhanced_extractor = EnhancedStudyCardExtractor()
        self.reviewer_analyzer = ReviewerNotesAnalyzer()
        
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Default ranking criteria
        self.default_criteria = [
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
    
    async def resolve_study_card_rankings(self, 
                                        study_cards: List[StudyCardForResolution],
                                        resolution_context: Optional[str] = None,
                                        ranking_criteria: Optional[List[str]] = None) -> BatchResolutionResult:
        """Resolve rankings for multiple study cards using LLM."""
        
        start_time = datetime.now()
        
        if not study_cards:
            raise ValueError("No study cards provided for resolution")
        
        # Use default criteria if none provided
        if ranking_criteria is None:
            ranking_criteria = self.default_criteria
        
        # Create resolution request
        request = LLMResolutionRequest(
            study_cards=study_cards,
            resolution_context=resolution_context or "Standard clinical trial ranking resolution",
            ranking_criteria=ranking_criteria,
            model=self.model
        )
        
        # Perform LLM resolution
        resolved_cards = []
        total_confidence = 0.0
        
        try:
            # Process study cards in batches to avoid rate limits
            batch_size = 5  # Process 5 study cards at a time
            for i in range(0, len(study_cards), batch_size):
                batch = study_cards[i:i + batch_size]
                batch_results = await self._resolve_batch(batch, request)
                resolved_cards.extend(batch_results)
                total_confidence += sum(r.confidence for r in batch_results)
                
                # Small delay between batches
                if i + batch_size < len(study_cards):
                    await asyncio.sleep(1)
            
            # Sort by enhanced score and assign relative positions
            resolved_cards.sort(key=lambda x: x.enhanced_score_1_100, reverse=True)
            for i, card in enumerate(resolved_cards):
                card.relative_position = i + 1
            
            # Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Generate resolution summary
            resolution_summary = self._generate_resolution_summary(resolved_cards, request)
            
            return BatchResolutionResult(
                resolved_cards=resolved_cards,
                resolution_summary=resolution_summary,
                total_confidence=total_confidence / len(resolved_cards) if resolved_cards else 0.0,
                processing_time=processing_time,
                model_used=self.model
            )
            
        except Exception as e:
            self.logger.error(f"Error during LLM resolution: {e}")
            raise
    
    async def _resolve_batch(self, 
                           study_cards: List[StudyCardForResolution],
                           request: LLMResolutionRequest) -> List[LLMResolutionResult]:
        """Resolve a batch of study cards."""
        
        # Prepare the prompt for the LLM
        prompt = self._create_resolution_prompt(study_cards, request)
        
        try:
            # Call OpenAI API
            response = await self._call_openai_api(prompt, request.model, request.temperature)
            
            # Parse the response
            resolved_cards = self._parse_llm_response(response, study_cards)
            
            return resolved_cards
            
        except Exception as e:
            self.logger.error(f"Error resolving batch: {e}")
            # Fallback to basic resolution
            return self._fallback_resolution(study_cards)
    
    def _create_resolution_prompt(self, 
                                study_cards: List[StudyCardForResolution],
                                request: LLMResolutionRequest) -> str:
        """Create the prompt for LLM resolution."""
        
        prompt = f"""You are an expert clinical trial analyst tasked with ranking study cards that have the same base quality score (1-10 scale).

Context: {request.resolution_context}

Ranking Criteria (in order of importance):
{chr(10).join(f"{i+1}. {criterion}" for i, criterion in enumerate(request.ranking_criteria))}

Your task is to expand the 1-10 scale to a 1-100 scale for relative ranking. The 1-100 score should reflect the relative quality within the same base score group.

Study Cards to Rank:
"""
        
        for i, card in enumerate(study_cards):
            prompt += f"""
Study Card {i+1}:
- Study ID: {card.study_id}
- Trial ID: {card.trial_id}
- Base Score (1-10): {card.base_score_1_10}
- Quality Score: {card.quality_score:.2f}
- Quality Confidence: {card.quality_confidence:.2f}

Key Data:
- Tone Analysis: {self._summarize_tone_analysis(card.tone_analysis)}
- Conflicts & Funding: {self._summarize_conflicts_funding(card.conflicts_funding)}
- Publication Details: {self._summarize_publication_details(card.publication_details)}
- Data Location: {self._summarize_data_location(card.data_location)}
- Reviewer Notes: {self._summarize_reviewer_notes(card.reviewer_notes)}

Please provide:
1. Enhanced Score (1-100): A score from 1-100 reflecting relative quality
2. Reasoning: Brief explanation of the score
3. Confidence: Your confidence in this assessment (0.0-1.0)
4. Key Factors: Top 3 factors influencing this ranking

Respond in JSON format:
{{
    "study_cards": [
        {{
            "study_id": {card.study_id},
            "trial_id": {card.trial_id},
            "enhanced_score_1_100": <score>,
            "reasoning": "<reasoning>",
            "confidence": <confidence>,
            "ranking_factors": ["<factor1>", "<factor2>", "<factor3>"]
        }}
    ]
}}
"""
        
        return prompt
    
    def _summarize_tone_analysis(self, tone_analysis: Dict[str, Any]) -> str:
        """Summarize tone analysis for the prompt."""
        if not tone_analysis:
            return "Not available"
        
        overall_tone = tone_analysis.get('overall_tone', 'unknown')
        claim_strength = tone_analysis.get('claim_strength', {})
        
        summary = f"Overall tone: {overall_tone}"
        if claim_strength:
            strengths = [f"{k}: {v}" for k, v in claim_strength.items()]
            summary += f", Claim strengths: {', '.join(strengths)}"
        
        return summary
    
    def _summarize_conflicts_funding(self, conflicts_funding: Dict[str, Any]) -> str:
        """Summarize conflicts and funding for the prompt."""
        if not conflicts_funding:
            return "Not available"
        
        conflicts_count = len(conflicts_funding.get('conflicts_of_interest', []))
        funding_count = len(conflicts_funding.get('funding_sources', []))
        
        return f"Conflicts: {conflicts_count}, Funding sources: {funding_count}"
    
    def _summarize_publication_details(self, publication_details: Dict[str, Any]) -> str:
        """Summarize publication details for the prompt."""
        if not publication_details:
            return "Not available"
        
        journal_type = publication_details.get('journal_type', 'unknown')
        impact_factor = publication_details.get('impact_factor', 'unknown')
        open_access = publication_details.get('open_access', 'unknown')
        
        return f"Journal: {journal_type}, Impact: {impact_factor}, OA: {open_access}"
    
    def _summarize_data_location(self, data_location: Dict[str, Any]) -> str:
        """Summarize data location for the prompt."""
        if not data_location:
            return "Not available"
        
        tables_count = len(data_location.get('tables', []))
        figures_count = len(data_location.get('figures', []))
        quotes_count = len(data_location.get('quote_spans', []))
        
        return f"Tables: {tables_count}, Figures: {figures_count}, Quotes: {quotes_count}"
    
    def _summarize_reviewer_notes(self, reviewer_notes: Dict[str, Any]) -> str:
        """Summarize reviewer notes for the prompt."""
        if not reviewer_notes:
            return "Not available"
        
        limitations_count = len(reviewer_notes.get('limitations', []))
        oddities_count = len(reviewer_notes.get('oddities', []))
        quality = reviewer_notes.get('quality_assessment', {}).get('overall_quality', 'unknown')
        
        return f"Limitations: {limitations_count}, Oddities: {oddities_count}, Quality: {quality}"
    
    async def _call_openai_api(self, prompt: str, model: str, temperature: float) -> str:
        """Call the OpenAI API."""
        
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert clinical trial analyst. Provide accurate, well-reasoned assessments based on the data provided."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=temperature,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            self.logger.error(f"OpenAI API call failed: {e}")
            raise
    
    def _parse_llm_response(self, 
                           response: str, 
                           study_cards: List[StudyCardForResolution]) -> List[LLMResolutionResult]:
        """Parse the LLM response into structured results."""
        
        try:
            # Parse JSON response
            response_data = json.loads(response)
            
            resolved_cards = []
            
            for card_data in response_data.get('study_cards', []):
                # Find matching study card
                matching_card = next(
                    (card for card in study_cards 
                     if card.study_id == card_data['study_id'] and card.trial_id == card_data['trial_id']),
                    None
                )
                
                if matching_card:
                    resolved_card = LLMResolutionResult(
                        study_id=card_data['study_id'],
                        trial_id=card_data['trial_id'],
                        base_score_1_10=matching_card.base_score_1_10,
                        enhanced_score_1_100=card_data['enhanced_score_1_100'],
                        resolution_reasoning=card_data['reasoning'],
                        confidence=card_data['confidence'],
                        ranking_factors=card_data['ranking_factors'],
                        relative_position=0,  # Will be set later
                        timestamp=datetime.now()
                    )
                    resolved_cards.append(resolved_card)
            
            return resolved_cards
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            self.logger.error(f"Error parsing LLM response: {e}")
            # Fallback to basic resolution
            return self._fallback_resolution(study_cards)
    
    def _fallback_resolution(self, study_cards: List[StudyCardForResolution]) -> List[LLMResolutionResult]:
        """Fallback resolution when LLM fails."""
        
        resolved_cards = []
        
        for i, card in enumerate(study_cards):
            # Simple fallback: use quality score to create enhanced score
            base_score = card.base_score_1_10
            quality_factor = card.quality_score
            
            # Convert to 1-100 scale within the base score range
            if base_score <= 3:
                enhanced_score = int(1 + (quality_factor * 30))
            elif base_score <= 6:
                enhanced_score = int(31 + (quality_factor * 30))
            else:
                enhanced_score = int(61 + (quality_factor * 39))
            
            resolved_card = LLMResolutionResult(
                study_id=card.study_id,
                trial_id=card.trial_id,
                base_score_1_10=base_score,
                enhanced_score_1_100=enhanced_score,
                resolution_reasoning="Fallback resolution using quality score",
                confidence=0.5,  # Lower confidence for fallback
                ranking_factors=["Quality score", "Base ranking", "Fallback algorithm"],
                relative_position=0,
                timestamp=datetime.now()
            )
            resolved_cards.append(resolved_card)
        
        return resolved_cards
    
    def _generate_resolution_summary(self, 
                                   resolved_cards: List[LLMResolutionResult],
                                   request: Optional[LLMResolutionRequest] = None) -> str:
        """Generate a summary of the resolution results."""
        
        if not resolved_cards:
            return "No study cards were resolved."
        
        # Calculate statistics
        total_cards = len(resolved_cards)
        avg_confidence = sum(card.confidence for card in resolved_cards) / total_cards
        score_ranges = {}
        
        for card in resolved_cards:
            base_score = card.base_score_1_10
            if base_score not in score_ranges:
                score_ranges[base_score] = []
            score_ranges[base_score].append(card.enhanced_score_1_100)
        
        model_used = request.model if request else "Unknown"
        summary = f"""
LLM Resolution Summary:
- Total study cards resolved: {total_cards}
- Model used: {model_used}
- Average confidence: {avg_confidence:.2f}
- Score distribution by base rank:
"""
        
        for base_score in sorted(score_ranges.keys()):
            scores = score_ranges[base_score]
            min_score = min(scores)
            max_score = max(scores)
            avg_score = sum(scores) / len(scores)
            summary += f"  Base rank {base_score}: Enhanced scores {min_score}-{max_score} (avg: {avg_score:.1f})\n"
        
        return summary.strip()
    
    def prepare_study_cards_for_resolution(self, 
                                         study_cards: List[Dict[str, Any]]) -> List[StudyCardForResolution]:
        """Prepare study cards for LLM resolution."""
        
        prepared_cards = []
        
        for card_data in study_cards:
            try:
                # Extract basic information
                study_id = card_data.get('study_id')
                trial_id = card_data.get('trial_id')
                base_score = card_data.get('base_score_1_10', 5)
                extracted_jsonb = card_data.get('extracted_jsonb', {})
                
                # Perform enhanced analysis if not already done
                enhanced_fields = self.enhanced_extractor.extract_enhanced_fields(extracted_jsonb)
                reviewer_notes = self.reviewer_analyzer.analyze_reviewer_notes(extracted_jsonb)
                
                # Calculate quality metrics
                quality_score = card_data.get('quality_score', 0.5)
                quality_confidence = card_data.get('quality_confidence', 0.5)
                
                # Convert enhanced fields to dictionaries for compatibility
                tone_analysis = asdict(enhanced_fields.get('tone_analysis', {})) if enhanced_fields.get('tone_analysis') else {}
                conflicts_funding = asdict(enhanced_fields.get('conflicts_funding', {})) if enhanced_fields.get('conflicts_funding') else {}
                publication_details = asdict(enhanced_fields.get('publication_details', {})) if enhanced_fields.get('publication_details') else {}
                data_location = asdict(enhanced_fields.get('data_location', {})) if enhanced_fields.get('data_location') else {}
                
                prepared_card = StudyCardForResolution(
                    study_id=study_id,
                    trial_id=trial_id,
                    base_score_1_10=base_score,
                    extracted_jsonb=extracted_jsonb,
                    tone_analysis=tone_analysis,
                    conflicts_funding=conflicts_funding,
                    publication_details=publication_details,
                    data_location=data_location,
                    reviewer_notes=asdict(reviewer_notes),
                    quality_score=quality_score,
                    quality_confidence=quality_confidence
                )
                
                prepared_cards.append(prepared_card)
                
            except Exception as e:
                self.logger.error(f"Error preparing study card {card_data.get('study_id', 'unknown')}: {e}")
                continue
        
        return prepared_cards
    
    def save_resolution_results(self, 
                              results: List[LLMResolutionResult],
                              db_session) -> None:
        """Save LLM resolution results to the database."""
        
        try:
            for result in results:
                # Create LLMResolutionScore record
                llm_score = LLMResolutionScore(
                    trial_id=result.trial_id,
                    base_score_1_10=result.base_score_1_10,
                    enhanced_score_1_100=result.enhanced_score_1_100,
                    resolution_reasoning=result.resolution_reasoning,
                    confidence=result.confidence,
                    ranking_factors=result.ranking_factors,
                    relative_position=result.relative_position,
                    model_used=self.model,
                    timestamp=result.timestamp
                )
                
                db_session.add(llm_score)
            
            db_session.commit()
            self.logger.info(f"Saved {len(results)} LLM resolution results to database")
            
        except Exception as e:
            self.logger.error(f"Error saving resolution results: {e}")
            db_session.rollback()
            raise


# Convenience function for synchronous usage
def resolve_study_card_rankings_sync(study_cards: List[StudyCardForResolution],
                                   resolution_context: Optional[str] = None,
                                   ranking_criteria: Optional[List[str]] = None) -> BatchResolutionResult:
    """Synchronous wrapper for resolve_study_card_rankings."""
    
    service = LLMResolutionService()
    return asyncio.run(service.resolve_study_card_rankings(
        study_cards, resolution_context, ranking_criteria
    ))
