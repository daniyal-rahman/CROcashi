"""
LLM-based entity matching.

This module provides an interface for using LLMs to validate entity matches.
The LLM is optional and disabled by default via feature flags.
"""
import json
import logging
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMMatchDecision:
    """Result from LLM matching decision."""
    match: bool
    confidence: float
    reasoning: str
    model_name: str


class LLMEntityMatcher:
    """
    Wrapper for LLM-based entity matching.
    
    Uses local LLM (llama.cpp) for inference. Gracefully handles missing
    dependencies or models by returning neutral decisions.
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize LLM matcher.
        
        Args:
            model_path: Path to GGUF model file (e.g., llama-3.1-70b.gguf)
        """
        self.model_path = model_path
        self.model = None
        self.model_name = "none"
        
        if model_path:
            self._load_model(model_path)
    
    def _load_model(self, model_path: str):
        """Load LLM model for inference."""
        try:
            from llama_cpp import Llama
            
            logger.info(f"Loading LLM model from {model_path}")
            
            self.model = Llama(
                model_path=model_path,
                n_gpu_layers=-1,  # Use all GPU layers
                n_ctx=4096,  # Context window
                n_batch=512,  # Batch size
                verbose=False
            )
            
            self.model_name = model_path.split('/')[-1]
            logger.info(f"✓ Loaded LLM model: {self.model_name}")
            
        except ImportError:
            logger.warning("llama-cpp-python not installed. LLM matching disabled.")
            logger.warning("Install with: pip install llama-cpp-python")
            self.model = None
        except Exception as e:
            logger.error(f"Failed to load LLM model: {e}")
            self.model = None
    
    def is_available(self) -> bool:
        """Check if LLM is available for inference."""
        return self.model is not None
    
    def match_entities(
        self,
        candidate_text: str,
        entity_name: str,
        entity_type: str,
        context: Dict,
        rule_confidence: float
    ) -> LLMMatchDecision:
        """
        Ask LLM to validate a potential entity match.
        
        Args:
            candidate_text: Text extracted from source
            entity_name: Name of existing entity
            entity_type: Type of entity (drug, disease, etc.)
            context: Additional context
            rule_confidence: Confidence from rule-based matcher
        
        Returns:
            LLMMatchDecision with match result
        """
        if not self.is_available():
            # Return neutral decision if LLM not available
            return LLMMatchDecision(
                match=False,
                confidence=0.0,
                reasoning="LLM not available",
                model_name="none"
            )
        
        prompt = self._build_prompt(
            candidate_text, entity_name, entity_type, context, rule_confidence
        )
        
        try:
            response = self.model(
                prompt,
                max_tokens=200,
                temperature=0.1,  # Low temperature for consistency
                stop=["```", "\n\n\n"]
            )
            
            decision = self._parse_response(response['choices'][0]['text'])
            decision.model_name = self.model_name
            return decision
            
        except Exception as e:
            logger.error(f"LLM inference error: {e}")
            return LLMMatchDecision(
                match=False,
                confidence=0.0,
                reasoning=f"LLM inference error: {str(e)}",
                model_name=self.model_name
            )
    
    def _build_prompt(
        self,
        candidate_text: str,
        entity_name: str,
        entity_type: str,
        context: Dict,
        rule_confidence: float
    ) -> str:
        """Build prompt for LLM."""
        # Clean context for display
        context_str = json.dumps(context, indent=2) if context else "{}"
        
        prompt = f"""You are an expert in biomedical entity matching.

**Candidate Entity:**
- Text: "{candidate_text}"
- Type: {entity_type}
- Context: {context_str}

**Potential Match:**
- Entity Name: "{entity_name}"
- Rule-based Confidence: {rule_confidence:.2f}

**Question:** Should these be matched?

Consider:
1. Abbreviations (NSCLC = Non-Small Cell Lung Cancer)
2. Synonyms
3. Different formulations
4. Stage/progression variations
5. Brand vs generic names

Respond with JSON only:
{{
    "match": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation"
}}"""
        
        return prompt
    
    def _parse_response(self, response_text: str) -> LLMMatchDecision:
        """Parse LLM response into decision."""
        try:
            # Try to extract JSON from response
            response_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
            
            # Parse JSON
            data = json.loads(response_text)
            
            return LLMMatchDecision(
                match=bool(data.get('match', False)),
                confidence=float(data.get('confidence', 0.0)),
                reasoning=str(data.get('reasoning', 'No reasoning provided')),
                model_name=self.model_name
            )
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Response text: {response_text}")
            
            # Return conservative decision
            return LLMMatchDecision(
                match=False,
                confidence=0.0,
                reasoning=f"Failed to parse LLM response: {str(e)}",
                model_name=self.model_name
            )

