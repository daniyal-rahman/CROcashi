"""
LLM evaluation engine for literature processing.

This module implements the periodic LLM evaluation system that determines when
to stop processing a trial based on accumulated evidence. It uses SPRT-style
stopping rules and manages the pull-on-demand full-text requests.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json

from .llm_client import create_llm_client
from .document_queue import DocumentCandidate

logger = logging.getLogger(__name__)


class StopDecision(Enum):
    """LLM evaluation stop decision."""
    CONTINUE = "continue"
    PROMOTE = "promote"      # P(short) >= theta_high
    PARK = "park"           # P(short) <= theta_low
    STOP = "stop"           # Plateau reached
    REQUEST_FULL_TEXT = "request_full_text"  # Need more data


@dataclass
class EvaluationResult:
    """Result of an LLM evaluation."""
    trial_id: str
    evaluation_round: int
    p_short_posterior: float
    documents_evaluated: int
    stop_decision: StopDecision
    reasoning: str
    confidence: float
    llm_tokens_used: int
    full_text_requests: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Ensure metadata is initialized."""
        if self.metadata is None:
            self.metadata = {}


@dataclass
class FullTextRequest:
    """Request for full text from LLM."""
    doc_id: str
    reason: str
    priority: str  # 'high', 'medium', 'low'
    requested_at: datetime = field(default_factory=datetime.now)


class LLMEvaluator:
    """
    Implements LLM-driven evaluation and stopping decisions.
    
    This class implements the SPRT-style stopping rules from the pruning strategy:
    - Stop when P(short) >= theta_high (promote to deep dive)
    - Stop when P(short) <= theta_low (park for 90 days)
    - Stop when plateau reached and next doc utility < delta
    """
    
    def __init__(self, config: Dict[str, Any], llm_client=None):
        """
        Initialize the LLM evaluator.
        
        Args:
            config: Configuration dictionary with evaluation parameters
            llm_client: LLM client for making evaluation calls
        """
        self.config = config
        self.llm_client = llm_client
        
        # Evaluation configuration
        self.eval_every_docs = config.get('eval_every_docs', 3)
        self.theta_high = config.get('theta_high', 0.80)
        self.theta_low = config.get('theta_low', 0.20)
        self.delta_min = config.get('delta_min', 0.05)
        self.plateau_epsilon = config.get('plateau_epsilon', 0.03)
        self.plateau_consecutive = config.get('plateau_consecutive', 2)
        
        # LLM configuration
        self.max_tokens_per_eval = config.get('tier2_llm_tokens_per_eval', 2000)
        self.evaluation_prompt_version = config.get('evaluation_prompt_version', '1.0')
        
        # Trial state tracking
        self._trial_evaluations: Dict[str, List[EvaluationResult]] = {}
        self._trial_posteriors: Dict[str, float] = {}
        self._trial_plateau_count: Dict[str, int] = {}
        self._trial_last_posterior: Dict[str, float] = {}
        
        # Statistics
        self.stats = {
            'evaluations_performed': 0,
            'trials_promoted': 0,
            'trials_parked': 0,
            'trials_stopped': 0,
            'full_text_requests': 0,
            'llm_failures': 0,
            'mock_evaluations': 0
        }
        
        # Flag to track if we've tried to create an LLM client
        self._llm_client_creation_attempted = False
        
        logger.info("LLM evaluator initialized with config: %s", config)
    
    def evaluate_trial_batch(self, trial_id: str, candidates: List[DocumentCandidate]) -> Optional[EvaluationResult]:
        """
        Evaluate a batch of trial candidates using LLM.
        
        Args:
            trial_id: Trial identifier
            candidates: List of document candidates to evaluate
            
        Returns:
            Evaluation result or None if evaluation fails
        """
        logger.info(f"🔍 LLM EVALUATOR: Starting evaluation for trial {trial_id}")
        logger.info(f"🔍 LLM EVALUATOR: Received {len(candidates)} candidates")
        
        if not candidates:
            logger.warning(f"🔍 LLM EVALUATOR: No candidates provided for trial {trial_id}")
            return None
            
        # Log candidate details
        for i, candidate in enumerate(candidates[:3]):  # Log first 3 candidates
            logger.info(f"🔍 LLM EVALUATOR: Candidate {i+1}: doc_id={candidate.doc_id}, u0={candidate.u0_score}, u1={getattr(candidate, 'u1_score', 'N/A')}")
        
        try:
            # Create LLM client if not provided
            if not self.llm_client:
                logger.info("🔍 LLM EVALUATOR: Creating new LLM client")
                from .llm_client import create_llm_client
                self.llm_client = create_llm_client()
            
            # Perform evaluation
            logger.info(f"🔍 LLM EVALUATOR: Calling _perform_llm_evaluation with {len(candidates)} candidates")
            result = self._perform_llm_evaluation(trial_id, candidates)
            logger.info(f"🔍 LLM EVALUATOR: Evaluation completed, result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"🔍 LLM EVALUATOR: Evaluation failed for trial {trial_id}: {e}")
            return None
    
    def should_stop_evaluation(self, trial_id: str, 
                             current_posterior: float) -> StopDecision:
        """
        Determine if evaluation should stop for a trial.
        
        Args:
            trial_id: Trial identifier
            current_posterior: Current P(short) posterior
            
        Returns:
            Stop decision
        """
        # Check high threshold (promote to deep dive)
        if current_posterior >= self.theta_high:
            self.stats['trials_promoted'] += 1
            logger.info("Trial %s: P(short)=%.3f >= %.3f, promoting to deep dive", 
                       trial_id, current_posterior, self.theta_high)
            return StopDecision.PROMOTE
        
        # Check low threshold (park for 90 days)
        if current_posterior <= self.theta_low:
            self.stats['trials_parked'] += 1
            logger.info("Trial %s: P(short)=%.3f <= %.3f, parking for 90 days", 
                       trial_id, current_posterior, self.theta_low)
            return StopDecision.PARK
        
        # Check for plateau
        if self._is_plateau_reached(trial_id):
            # Check if next document utility is below threshold
            next_doc_utility = self._get_next_document_utility(trial_id)
            if next_doc_utility < self.delta_min:
                self.stats['trials_stopped'] += 1
                logger.info("Trial %s: plateau reached, next doc utility=%.3f < %.3f, stopping", 
                           trial_id, next_doc_utility, self.delta_min)
                return StopDecision.STOP
        
        return StopDecision.CONTINUE
    
    def request_full_text(self, doc_id: str, reason: str) -> bool:
        """
        Request full text for a document (pull-on-demand rule).
        
        Args:
            doc_id: Document identifier
            reason: Reason for requesting full text
            
        Returns:
            True if request is approved
        """
        # Check budget limits
        if not self._check_budget_limits():
            logger.warning("Full text request denied for doc %s: budget limit reached", doc_id)
            return False
        
        # Log the request
        logger.info("Full text request for doc %s: %s", doc_id, reason)
        self.stats['full_text_requests'] += 1
        
        return True
    
    def get_trial_evaluation_history(self, trial_id: str) -> List[EvaluationResult]:
        """
        Get evaluation history for a trial.
        
        Args:
            trial_id: Trial identifier
            
        Returns:
            List of evaluation results
        """
        return self._trial_evaluations.get(trial_id, [])
    
    def get_trial_current_posterior(self, trial_id: str) -> Optional[float]:
        """
        Get current P(short) posterior for a trial.
        
        Args:
            trial_id: Trial identifier
            
        Returns:
            Current posterior or None if not available
        """
        return self._trial_posteriors.get(trial_id)
    
    def get_evaluation_stats(self) -> Dict[str, Any]:
        """
        Get evaluation statistics.
        
        Returns:
            Dictionary with evaluation statistics
        """
        return {
            **self.stats,
            'trials_evaluated': len(self._trial_evaluations),
            'avg_tokens_per_eval': (
                self.stats['total_tokens_used'] / max(1, self.stats['evaluations_performed'])
            )
        }
    
    def _ensure_llm_client(self) -> bool:
        """
        Ensure LLM client is available, creating one if necessary.
        
        Returns:
            True if LLM client is available, False otherwise
        """
        if self.llm_client:
            return True
            
        # Only try to create once to avoid repeated failures
        if self._llm_client_creation_attempted:
            return False
            
        self._llm_client_creation_attempted = True
        
        try:
            from .llm_client import create_llm_client
            self.llm_client = create_llm_client("openai")
            logger.info("Created default OpenAI LLM client")
            return True
        except Exception as e:
            logger.warning(f"Failed to create LLM client (will use mock evaluation): {e}")
            self.stats['llm_failures'] += 1
            return False
    
    def _perform_llm_evaluation(self, trial_id: str, candidates: List[DocumentCandidate]) -> Optional[EvaluationResult]:
        """
        Perform LLM evaluation for a trial.
        
        Args:
            trial_id: Trial identifier
            candidates: List of document candidates to evaluate
            
        Returns:
            Evaluation result or None if evaluation fails
        """
        # Ensure LLM client is available
        if not self._ensure_llm_client():
            logger.info("LLM client not available, using mock evaluation")
            self.stats['mock_evaluations'] += 1
            return self._mock_evaluation(trial_id, candidates)
        
        try:
            # Convert DocumentCandidate objects to the expected dictionary format
            doc_summaries = []
            for candidate in candidates:
                summary = {
                    'doc_id': candidate.doc_id,
                    'title': getattr(candidate, 'title', f'Document {candidate.doc_id}'),
                    'source_type': getattr(candidate, 'source_type', 'Unknown'),
                    'key_findings': getattr(candidate, 'abstract', 'No abstract available'),
                    'u0_score': candidate.u0_score,
                    'u1_score': getattr(candidate, 'u1_score', None)
                }
                doc_summaries.append(summary)
            
            logger.info(f"🔍 LLM EVALUATOR: Converted {len(candidates)} candidates to {len(doc_summaries)} summaries")
            
            # Prepare evaluation prompt
            prompt = self._build_evaluation_prompt(trial_id, doc_summaries)
            
            # Make LLM call
            response = self.llm_client.evaluate(prompt, max_tokens=self.max_tokens_per_eval)
            
            # Parse response
            evaluation_data = self._parse_llm_response(response)
            
            # Create evaluation result
            result = EvaluationResult(
                trial_id=trial_id,
                evaluation_round=len(self._trial_evaluations.get(trial_id, [])) + 1,
                p_short_posterior=evaluation_data['p_short'],
                documents_evaluated=len(doc_summaries),
                stop_decision=self._determine_stop_decision(evaluation_data['p_short']),
                reasoning=evaluation_data.get('reasoning', ''),
                confidence=evaluation_data.get('confidence', 0.8),
                llm_tokens_used=response.get('tokens_used', 0) if isinstance(response, dict) else 0,
                full_text_requests=evaluation_data.get('full_text_requests', [])
            )
            
            return result
            
        except Exception as e:
            logger.error("LLM evaluation failed: %s", e)
            self.stats['llm_failures'] += 1
            return self._mock_evaluation(trial_id, candidates)
    
    def _build_evaluation_prompt(self, trial_id: str, 
                                doc_summaries: List[Dict[str, Any]]) -> str:
        """
        Build the evaluation prompt for the LLM.
        
        Args:
            trial_id: Trial identifier
            doc_summaries: Document summaries to evaluate
            
        Returns:
            Formatted prompt string
        """
        prompt = f"""
        You are evaluating clinical trial {trial_id} based on the following document summaries.
        
        Your task is to assess the probability P(short) that this trial will have a negative outcome
        (e.g., failed primary endpoint, no significant difference, terminated for futility).
        
        Document Summaries:
        """
        
        for i, summary in enumerate(doc_summaries):
            prompt += f"\n{i+1}. {summary.get('title', 'Unknown')}"
            prompt += f"\n   Type: {summary.get('source_type', 'Unknown')}"
            prompt += f"\n   Key findings: {summary.get('key_findings', 'None')}"
            prompt += f"\n   U0 score: {summary.get('u0_score', 'Unknown')}"
            if summary.get('u1_score') is not None:
                prompt += f"\n   U1 score: {summary.get('u1_score')}"
        
        prompt += f"""
        
        Based on these summaries, please provide:
        1. P(short): Probability of negative outcome (0.0 to 1.0)
        2. Reasoning: Brief explanation of your assessment
        3. Confidence: Your confidence in this assessment (0.0 to 1.0)
        4. Full text requests: List any documents where you need full text to make a better assessment
        
        Respond in JSON format:
        {{
            "p_short": 0.45,
            "reasoning": "Mixed evidence with some negative signals...",
            "confidence": 0.7,
            "full_text_requests": [
                {{"doc_id": "doc123", "reason": "Need to check endpoint definition"}}
            ]
        }}
        """
        
        return prompt
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM response to extract evaluation data.
        
        Args:
            response: LLM response string
            
        Returns:
            Parsed evaluation data
        """
        try:
            # The new LLM client returns the response string directly
            content = response if isinstance(response, str) else str(response)
            
            # Try to parse JSON
            import json
            data = json.loads(content)
            
            return {
                'p_short': float(data.get('p_short', 0.5)),
                'reasoning': data.get('reasoning', ''),
                'confidence': float(data.get('confidence', 0.8)),
                'full_text_requests': data.get('full_text_requests', [])
            }
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("Failed to parse LLM response: %s", e)
            return {
                'p_short': 0.5,
                'reasoning': 'Failed to parse LLM response',
                'confidence': 0.5,
                'full_text_requests': []
            }
    
    def _mock_evaluation(self, trial_id: str, 
                        candidates: List[DocumentCandidate]) -> EvaluationResult:
        """
        Create a mock evaluation result for testing.
        
        Args:
            trial_id: Trial identifier
            candidates: Document candidates
            
        Returns:
            Mock evaluation result
        """
        # Simple heuristic-based evaluation
        total_score = 0.0
        for candidate in candidates:
            total_score += candidate.u0_score
            if hasattr(candidate, 'u1_score') and candidate.u1_score is not None:
                total_score += candidate.u1_score
        
        avg_score = total_score / (len(candidates) * 2) if candidates else 0.5
        
        # Higher score = lower P(short)
        p_short = max(0.1, min(0.9, 1.0 - avg_score))
        
        return EvaluationResult(
            trial_id=trial_id,
            evaluation_round=len(self._trial_evaluations.get(trial_id, [])) + 1,
            p_short_posterior=p_short,
            documents_evaluated=len(candidates),
            stop_decision=self._determine_stop_decision(p_short),
            reasoning=f"Mock evaluation based on average scores (avg={avg_score:.3f})",
            confidence=0.6,
            llm_tokens_used=0,
            full_text_requests=[]
        )
    
    def _determine_stop_decision(self, p_short: float) -> StopDecision:
        """
        Determine stop decision based on P(short) value.
        
        Args:
            p_short: P(short) posterior value
            
        Returns:
            Stop decision
        """
        if p_short >= self.theta_high:
            return StopDecision.PROMOTE
        elif p_short <= self.theta_low:
            return StopDecision.PARK
        else:
            return StopDecision.CONTINUE
    
    def _check_plateau(self, trial_id: str) -> None:
        """Check if trial has reached a plateau in posterior updates."""
        if trial_id not in self._trial_last_posterior:
            return
        
        current_posterior = self._trial_posteriors.get(trial_id, 0.5)
        last_posterior = self._trial_last_posterior.get(trial_id, 0.5)
        
        delta = abs(current_posterior - last_posterior)
        
        if delta < self.plateau_epsilon:
            self._trial_plateau_count[trial_id] = self._trial_plateau_count.get(trial_id, 0) + 1
        else:
            self._trial_plateau_count[trial_id] = 0
    
    def _is_plateau_reached(self, trial_id: str) -> bool:
        """Check if plateau threshold has been reached."""
        plateau_count = self._trial_plateau_count.get(trial_id, 0)
        return plateau_count >= self.plateau_consecutive
    
    def _get_next_document_utility(self, trial_id: str) -> float:
        """
        Get the utility of the next best document for a trial.
        
        Args:
            trial_id: Trial identifier
            
        Returns:
            Utility score of next best document
        """
        # This would typically come from the document queue
        # For now, return a default value
        return 0.1
    
    def _check_budget_limits(self) -> bool:
        """
        Check if budget limits allow full text requests.
        
        Returns:
            True if request is allowed
        """
        # Simple budget check - could be more sophisticated
        max_requests = self.config.get('max_full_text_requests_per_trial', 2)
        current_requests = self.stats['full_text_requests']
        
        return current_requests < max_requests
    
    def _create_default_result(self, trial_id: str, stop_decision: StopDecision, 
                             error_message: str = None) -> EvaluationResult:
        """Create a default evaluation result."""
        return EvaluationResult(
            trial_id=trial_id,
            evaluation_round=0,
            p_short_posterior=0.5,
            documents_evaluated=0,
            stop_decision=stop_decision,
            reasoning=error_message or "Default evaluation result",
            confidence=0.5,
            llm_tokens_used=0,
            full_text_requests=[]
        )
