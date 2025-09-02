"""
FactsBin LLM Selector

LLM worker that selects factual sentences from provided spans and classifies them by type.
Implements span-limited processing to prevent hallucinations and ensure auditability.
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from ..base_worker import BaseWorker, WorkerResult
from ....db.models import BaseSpan, DerivedSpan
from ....db.session import get_session
from ...config.span_config_loader import get_span_config


@dataclass
class FactCandidate:
    """A candidate fact extracted from text."""
    text: str
    span_id: int
    confidence: float
    type: Optional[str] = None
    relevance_score: Optional[float] = None
    has_numeric: bool = False
    units: Optional[str] = None


@dataclass
class FactClassification:
    """Classification result for a fact candidate."""
    candidate: FactCandidate
    is_fact: bool
    relevance_score: float
    confidence: float
    reasoning: str
    span_id: int
    fact_type: Optional[str] = None


class FactsBinSelector(BaseWorker):
    """LLM worker for selecting and classifying facts from spans."""
    
    def __init__(self):
        super().__init__(name="FactsBinSelector", version="1.0.0")
        self.config = get_span_config()
        
        # Supported fact types
        self.fact_types = [
            "methods_detail",
            "operational", 
            "limitation",
            "safety",
            "misc"
        ]
        
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Process spans to extract and classify facts."""
        doc_id = inputs.get("doc_id")
        spans = inputs.get("spans", [])
        max_facts = inputs.get("max_facts", 10)
        
        if not doc_id:
            return WorkerResult(
                success=False,
                output=None,
                error_message="doc_id is required"
            )
        
        if not spans:
            return WorkerResult(
                success=False,
                output=None,
                error_message="spans list is required"
            )
        
        try:
            # Generate candidates from spans
            candidates = self._generate_candidates(spans)
            
            # Classify candidates using LLM
            classifications = self._classify_candidates(candidates, max_facts)
            
            # Filter to only facts
            facts = [c for c in classifications if c.is_fact]
            
            # Sort by relevance score
            facts.sort(key=lambda x: x.relevance_score, reverse=True)
            
            # Take top N facts
            top_facts = facts[:max_facts]
            
            return WorkerResult(
                success=True,
                output={
                    "facts_selected": len(top_facts),
                    "total_candidates": len(candidates),
                    "facts": [
                        {
                            "text": fact.candidate.text,
                            "type": fact.fact_type,
                            "relevance_score": fact.relevance_score,
                            "confidence": fact.confidence,
                            "span_id": fact.span_id,
                            "has_numeric": fact.candidate.has_numeric,
                            "units": fact.candidate.units,
                            "reasoning": fact.reasoning
                        }
                        for fact in top_facts
                    ],
                    "classification_summary": self._get_classification_summary(classifications)
                },
                metadata={
                    "doc_id": doc_id,
                    "max_facts": max_facts,
                    "fact_types": self.fact_types
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error processing facts for document {doc_id}: {str(e)}"
            )
    
    def _generate_candidates(self, spans: List[Dict[str, Any]]) -> List[FactCandidate]:
        """Generate fact candidates from spans."""
        candidates = []
        
        for span in spans:
            # Extract span text and ID
            span_text = span.get("text", "")
            span_id = span.get("span_id")
            
            if not span_text or not span_id:
                continue
            
            # Check if span contains factual content
            if self._is_potential_fact(span_text):
                candidate = FactCandidate(
                    text=span_text,
                    span_id=span_id,
                    confidence=0.8,  # Default confidence
                    has_numeric=self._contains_numeric(span_text),
                    units=self._extract_units(span_text)
                )
                candidates.append(candidate)
        
        return candidates
    
    def _is_potential_fact(self, text: str) -> bool:
        """Check if text contains potential factual content."""
        text_lower = text.lower()
        
        # Skip very short text
        if len(text.strip()) < 20:
            return False
        
        # Skip obvious non-facts
        non_fact_indicators = [
            "abstract", "introduction", "conclusion", "discussion",
            "figure", "table", "supplementary", "appendix"
        ]
        
        if any(indicator in text_lower for indicator in non_fact_indicators):
            return False
        
        # Enhanced factual indicators based on policy requirements
        # Accept sentences with number/unit or methods keywords (RECIST, Kaplan-Meier, Gehan, interim, randomized/blinded)
        fact_indicators = [
            # Numbers and units
            "patients", "subjects", "participants", "cohort",
            "median", "mean", "rate", "percentage", "response",
            "survival", "progression", "toxicity", "adverse",
            "dose", "schedule", "protocol", "criteria",
            "analysis", "evaluation", "assessment", "measurement",
            
            # Methods keywords (RECIST, Kaplan-Meier, Gehan, interim, randomized/blinded)
            "recist", "kaplan", "meier", "gehan", "interim",
            "randomized", "randomised", "blinded", "blind", "open label",
            "log-rank", "cox", "proportional hazards",
            
            # Additional clinical trial keywords
            "endpoint", "primary", "secondary", "objective",
            "efficacy", "safety", "tolerability", "pharmacokinetics",
            "pharmacodynamics", "bioavailability", "clearance",
            "half-life", "volume of distribution", "area under curve",
            "maximum concentration", "time to maximum",
            
            # Statistical terms
            "confidence interval", "p-value", "p value", "statistical",
            "significance", "power", "sample size", "enrollment",
            "randomization", "stratification", "blocking",
            
            # Clinical assessment terms
            "response rate", "complete response", "partial response",
            "stable disease", "progressive disease", "objective response",
            "duration of response", "time to progression", "overall survival",
            "progression-free survival", "event-free survival",
            
            # Adverse events
            "adverse event", "serious adverse event", "grade",
            "ctcae", "common terminology criteria", "toxicity",
            "side effect", "treatment emergent", "treatment-related"
        ]
        
        return any(indicator in text_lower for indicator in fact_indicators)
    
    def _contains_numeric(self, text: str) -> bool:
        """Check if text contains numeric values."""
        import re
        # Enhanced numeric pattern to catch more clinical trial numbers
        numeric_patterns = [
            r'\b\d+(?:\.\d+)?\s*(?:%|percent|mg|kg|ml|g|mcg|ng|pg)\b',  # Units
            r'\b\d+(?:\.\d+)?\s*(?:days?|weeks?|months?|years?|cycles?|hours?|minutes?)\b',  # Time
            r'\b\d+(?:\.\d+)?\s*(?:patients?|subjects?|participants?|cohorts?)\b',  # Counts
            r'\b\d+(?:\.\d+)?\s*(?:mg/kg|mg/m2|ml/min|ml/kg|ng/ml|pg/ml)\b',  # Combined units
            r'\b\d+(?:\.\d+)?\s*(?:confidence interval|ci|hazard ratio|hr|odds ratio|or)\b',  # Statistics
            r'\b\d+(?:\.\d+)?\s*(?:response rate|survival rate|progression rate)\b',  # Rates
            r'\b\d+(?:\.\d+)?\s*(?:grade|level|score|scale)\b',  # Grading/scoring
            r'\b\d+(?:\.\d+)?\s*(?:fold|times|x)\b',  # Multiples
            r'\b\d+(?:\.\d+)?\s*(?:median|mean|average|range)\b',  # Statistical measures
        ]
        
        for pattern in numeric_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _extract_units(self, text: str) -> Optional[str]:
        """Extract units from text if present."""
        import re
        
        # Enhanced unit patterns for clinical trials
        unit_patterns = [
            r'(\d+(?:\.\d+)?)\s*(%)',  # Percentages
            r'(\d+(?:\.\d+)?)\s*(mg|kg|ml|g|mcg|ng|pg)',  # Weight/volume
            r'(\d+(?:\.\d+)?)\s*(days?|weeks?|months?|years?|cycles?|hours?|minutes?)',  # Time
            r'(\d+(?:\.\d+)?)\s*(patients?|subjects?|participants?|cohorts?)',  # Counts
            r'(\d+(?:\.\d+)?)\s*(mg/kg|mg/m2|ml/min|ml/kg|ng/ml|pg/ml)',  # Combined units
            r'(\d+(?:\.\d+)?)\s*(confidence interval|ci|hazard ratio|hr|odds ratio|or)',  # Statistics
            r'(\d+(?:\.\d+)?)\s*(response rate|survival rate|progression rate)',  # Rates
            r'(\d+(?:\.\d+)?)\s*(grade|level|score|scale)',  # Grading/scoring
            r'(\d+(?:\.\d+)?)\s*(fold|times|x)',  # Multiples
            r'(\d+(?:\.\d+)?)\s*(median|mean|average|range)',  # Statistical measures
        ]
        
        for pattern in unit_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(2)
        
        return None
    
    def _classify_candidates(self, candidates: List[FactCandidate], max_facts: int) -> List[FactClassification]:
        """Classify candidates using LLM (simulated for now)."""
        classifications = []
        
        for candidate in candidates:
            # Simulate LLM classification
            classification = self._simulate_llm_classification(candidate)
            classifications.append(classification)
        
        return classifications
    
    def _simulate_llm_classification(self, candidate: FactCandidate) -> FactClassification:
        """Simulate LLM classification of a fact candidate."""
        import random
        
        # Determine if this is likely a fact based on content
        text_lower = candidate.text.lower()
        
        # Check for fact indicators
        fact_indicators = {
            "methods_detail": ["protocol", "criteria", "assessment", "evaluation", "analysis"],
            "operational": ["dose", "schedule", "administration", "treatment", "procedure"],
            "limitation": ["limitation", "restriction", "exclusion", "constraint", "caveat"],
            "safety": ["toxicity", "adverse", "safety", "tolerability", "side effect"],
            "misc": ["demographic", "baseline", "characteristic", "feature"]
        }
        
        # Determine fact type
        fact_type = None
        for ftype, indicators in fact_indicators.items():
            if any(indicator in text_lower for indicator in indicators):
                fact_type = ftype
                break
        
        if not fact_type:
            fact_type = "misc"
        
        # Determine if it's a fact (most candidates are facts)
        is_fact = random.random() > 0.1  # 90% chance of being a fact
        
        # Calculate relevance score
        relevance_score = self._calculate_relevance_score(candidate, fact_type)
        
        # Generate reasoning
        reasoning = self._generate_reasoning(candidate, is_fact, fact_type, relevance_score)
        
        return FactClassification(
            candidate=candidate,
            is_fact=is_fact,
            fact_type=fact_type if is_fact else None,
            relevance_score=relevance_score,
            confidence=0.8,
            reasoning=reasoning,
            span_id=candidate.span_id
        )
    
    def _calculate_relevance_score(self, candidate: FactCandidate, fact_type: str) -> float:
        """Calculate relevance score for a fact candidate."""
        score = 0.5  # Base score
        
        # Boost for numeric content
        if candidate.has_numeric:
            score += 0.2
        
        # Boost for specific fact types
        type_boosts = {
            "methods_detail": 0.3,
            "operational": 0.25,
            "limitation": 0.2,
            "safety": 0.3,
            "misc": 0.1
        }
        score += type_boosts.get(fact_type, 0.0)
        
        # Boost for key methods keywords (RECIST, Kaplan-Meier, Gehan, interim, randomized/blinded)
        text_lower = candidate.text.lower()
        key_methods_keywords = [
            "recist", "kaplan", "meier", "gehan", "interim",
            "randomized", "randomised", "blinded", "blind", "open label",
            "log-rank", "cox", "proportional hazards"
        ]
        
        methods_keyword_count = sum(1 for keyword in key_methods_keywords if keyword in text_lower)
        if methods_keyword_count > 0:
            score += 0.3  # Significant boost for methods keywords
        
        # Boost for statistical terms
        statistical_keywords = [
            "confidence interval", "p-value", "p value", "statistical",
            "significance", "power", "sample size", "enrollment",
            "hazard ratio", "odds ratio", "median", "mean"
        ]
        
        stat_keyword_count = sum(1 for keyword in statistical_keywords if keyword in text_lower)
        if stat_keyword_count > 0:
            score += 0.2  # Boost for statistical terms
        
        # Boost for clinical assessment terms
        clinical_keywords = [
            "response rate", "complete response", "partial response",
            "stable disease", "progressive disease", "objective response",
            "duration of response", "time to progression", "overall survival",
            "progression-free survival", "event-free survival"
        ]
        
        clinical_keyword_count = sum(1 for keyword in clinical_keywords if keyword in text_lower)
        if clinical_keyword_count > 0:
            score += 0.25  # Boost for clinical terms
        
        # Boost for longer, more detailed text
        text_length = len(candidate.text)
        if text_length > 100:
            score += 0.1
        elif text_length > 50:
            score += 0.05
        
        # Normalize to 0-1 range
        return min(1.0, max(0.0, score))
    
    def _generate_reasoning(self, candidate: FactCandidate, is_fact: bool, 
                           fact_type: str, relevance_score: float) -> str:
        """Generate reasoning for the classification."""
        if not is_fact:
            return "Text does not contain factual information suitable for extraction."
        
        reasoning_parts = [f"Contains factual information about {fact_type.replace('_', ' ')}"]
        
        if candidate.has_numeric:
            reasoning_parts.append("Includes numeric data")
        
        if candidate.units:
            reasoning_parts.append(f"Specifies units ({candidate.units})")
        
        if relevance_score > 0.7:
            reasoning_parts.append("High relevance to study outcomes")
        elif relevance_score > 0.5:
            reasoning_parts.append("Moderate relevance to study outcomes")
        else:
            reasoning_parts.append("Lower relevance but still factual")
        
        return ". ".join(reasoning_parts) + "."
    
    def _get_classification_summary(self, classifications: List[FactClassification]) -> Dict[str, Any]:
        """Get a summary of classification results."""
        total = len(classifications)
        facts = [c for c in classifications if c.is_fact]
        non_facts = [c for c in classifications if not c.is_fact]
        
        # Count by type
        type_counts = {}
        for fact in facts:
            fact_type = fact.fact_type or "unknown"
            type_counts[fact_type] = type_counts.get(fact_type, 0) + 1
        
        # Average relevance scores
        avg_relevance = sum(f.relevance_score for f in facts) / len(facts) if facts else 0.0
        
        return {
            "total_candidates": total,
            "facts_found": len(facts),
            "non_facts": len(non_facts),
            "fact_rate": len(facts) / total if total > 0 else 0.0,
            "type_distribution": type_counts,
            "average_relevance": avg_relevance
        }
    
    def validate_fact_span_references(self, facts: List[Dict[str, Any]], doc_id: int) -> Dict[str, Any]:
        """Validate that all facts have valid span references."""
        try:
            with get_db_session() as session:
                # Get all span IDs for this document
                base_spans = session.query(BaseSpan).filter(BaseSpan.doc_id == doc_id).all()
                derived_spans = session.query(DerivedSpan).filter(DerivedSpan.doc_id == doc_id).all()
                
                all_span_ids = {span.span_id for span in base_spans}
                all_span_ids.update({span.derived_id for span in derived_spans})
                
                validation_results = {
                    "doc_id": doc_id,
                    "total_facts": len(facts),
                    "valid_spans": 0,
                    "invalid_spans": 0,
                    "span_validation": []
                }
                
                for fact in facts:
                    span_id = fact.get("span_id")
                    if span_id in all_span_ids:
                        validation_results["valid_spans"] += 1
                        validation_results["span_validation"].append({
                            "fact_text": fact.get("text", "")[:50] + "...",
                            "span_id": span_id,
                            "valid": True
                        })
                    else:
                        validation_results["invalid_spans"] += 1
                        validation_results["span_validation"].append({
                            "fact_text": fact.get("text", "")[:50] + "...",
                            "span_id": span_id,
                            "valid": False,
                            "error": "Span ID not found in document"
                        })
                
                return validation_results
                
        except Exception as e:
            return {"error": str(e)}
    
    def get_facts_by_type(self, facts: List[Dict[str, Any]], fact_type: str) -> List[Dict[str, Any]]:
        """Get facts filtered by type."""
        return [fact for fact in facts if fact.get("type") == fact_type]
    
    def get_high_relevance_facts(self, facts: List[Dict[str, Any]], threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Get facts with relevance score above threshold."""
        return [fact for fact in facts if fact.get("relevance_score", 0) >= threshold]
    
    def export_facts_to_claims(self, facts: List[Dict[str, Any]], doc_id: int) -> List[Dict[str, Any]]:
        """Export facts to Claim format for downstream processing."""
        claims = []
        
        for fact in facts:
            claim = {
                "type": fact.get("type", "misc"),
                "text": fact.get("text", ""),
                "span_ids": [fact.get("span_id")],
                "has_numeric": fact.get("has_numeric", False),
                "units": fact.get("units"),
                "relevance_score": fact.get("relevance_score", 0.0),
                "confidence": fact.get("confidence", 0.8),
                "doc_id": doc_id,
                "metadata": {
                    "source": "factsbin_selector",
                    "reasoning": fact.get("reasoning", ""),
                    "extracted_at": "2024-01-01T00:00:00Z"  # Should use actual timestamp
                }
            }
            claims.append(claim)
        
        return claims
