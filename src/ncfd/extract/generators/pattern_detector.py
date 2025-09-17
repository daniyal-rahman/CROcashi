"""
Pattern Family Detector

LLM-driven pattern detection for F1-F9 Pattern Families system.
Replaces the old gate assessment generator with pattern-based detection.
"""

import logging
import yaml
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from ..risk_assessment.models import PatternDetection, SeverityLevel
from ...llm import BaseLLMGenerator

logger = logging.getLogger(__name__)


class PatternFamilyDetector(BaseLLMGenerator):
    """LLM-driven pattern detection for Pattern Families system."""
    
    def __init__(self, config_path: str = "config/pattern_families.yaml", llm_config: Optional[Dict[str, Any]] = None):
        super().__init__("PatternFamilyDetector", "1.0.0", llm_config)
        self.config_path = config_path
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config()
        self.patterns = self._load_patterns()
    
    async def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect patterns using Pattern Families system.
        
        Args:
            inputs: {
                "raw_doc_text": str,
                "doc_id": str,
                "trial_context": Dict[str, Any]
            }
            
        Returns:
            {
                "pattern_detections": List[PatternDetection],
                "success": bool,
                "error_message": Optional[str]
            }
        """
        try:
            raw_doc_text = inputs.get("raw_doc_text", "")
            doc_id = inputs.get("doc_id", "")
            trial_context = inputs.get("trial_context", {})
            
            if not raw_doc_text:
                return {
                    "pattern_detections": [],
                    "success": False,
                    "error_message": "No document text provided"
                }
            
            # Detect patterns
            detections = await self.detect_patterns(doc_id, [{"content": raw_doc_text, "doc_id": doc_id}], trial_context)
            
            return {
                "pattern_detections": detections,
                "success": True,
                "error_message": None
            }
            
        except Exception as e:
            self.logger.error(f"Pattern detection failed: {str(e)}")
            return {
                "pattern_detections": [],
                "success": False,
                "error_message": str(e)
            }
    
    def _load_config(self) -> Dict[str, Any]:
        """Load Pattern Families configuration."""
        config_file = Path(self.config_path)
        if not config_file.exists():
            self.logger.warning(f"Config file not found: {self.config_path}")
            return {}
        
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def _load_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Load pattern configurations."""
        patterns = {}
        
        if 'families' not in self.config:
            return patterns
        
        for family_id, family_data in self.config['families'].items():
            for pattern_id, pattern_data in family_data.get('patterns', {}).items():
                full_pattern_id = f"{family_id}{pattern_id}"
                patterns[full_pattern_id] = {
                    'family_id': family_id,
                    'pattern_id': full_pattern_id,
                    'name': pattern_data.get('name', ''),
                    'description': pattern_data.get('description', ''),
                    'cue_phrases': pattern_data.get('cue_phrases', []),
                    'severity_rules': pattern_data.get('severity_rules', {})
                }
        
        return patterns
    
    async def detect_patterns(self, 
                            trial_id: str,
                            documents: List[Dict[str, Any]],
                            trial_context: Dict[str, Any]) -> List[PatternDetection]:
        """Detect patterns using LLM."""
        
        # Build prompt
        prompt = self._build_detection_prompt(documents, trial_context)
        
        # Call LLM
        response = await self._extract_with_llm("", trial_context, prompt)
        
        # Parse response
        detections = self._parse_llm_response(response)
        
        # Apply deterministic guards
        detections = self._apply_deterministic_guards(detections, trial_context)
        
        return detections
    
    def _get_data_key(self) -> str:
        """Return the key for the main data in the LLM response."""
        return "pattern_detections"
    
    def _build_standard_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build the standard prompt for the first attempt."""
        documents = [{"content": doc_text, "doc_id": doc_id}]
        return self._build_detection_prompt(documents, trial_context)
    
    def _build_simplified_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build a simplified prompt for the second attempt."""
        documents = [{"content": doc_text[:2000], "doc_id": doc_id}]  # Truncate for simplicity
        return self._build_detection_prompt(documents, trial_context)
    
    def _build_minimal_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build a minimal prompt for the third attempt."""
        documents = [{"content": doc_text[:1000], "doc_id": doc_id}]  # Further truncate
        return self._build_detection_prompt(documents, trial_context)
    
    async def _extract_with_llm(self, doc_text: str, trial_context: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Extract data using LLM with the given prompt."""
        try:
            response = await self.call_llm(
                messages=[prompt],
                temperature=0.1,
                max_tokens=2000,
                json_output=True
            )
            
            # Parse the response
            result = response.content
            if isinstance(result, str):
                import json
                result = json.loads(result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"LLM pattern detection failed: {e}")
            return {"pattern_detections": []}
    
    def _build_detection_prompt(self, documents: List[Dict[str, Any]], trial_context: Dict[str, Any]) -> str:
        """Build LLM prompt for pattern detection."""
        
        # Extract relevant text from documents
        text_slices = self._extract_text_slices(documents)
        
        # Build pattern cards
        pattern_cards = self._build_pattern_cards()
        
        prompt = f"""
You are a clinical trial risk assessment expert. Analyze the following trial documents and identify pattern matches across all families F1-F9.

Trial Context:
- Trial ID: {trial_context.get('trial_id', 'Unknown')}
- Indication: {trial_context.get('indication', 'Unknown')}
- Phase: {trial_context.get('phase', 'Unknown')}

Pattern Cards:
{pattern_cards}

Document Text Slices:
{text_slices}

For each family F1-F9, identify 0-3 applicable patterns with:
- family_id (F1-F9)
- pattern_id (F1P1-F9P4)  
- severity (0-3: Grey/Yellow/Amber/Red)
- confidence (0-1)
- rationale (brief explanation)
- evidence_spans (doc_id + snippet_hash)

Severity Rubric:
- 3 (Red): Likely to materially invalidate result or approval path
- 2 (Amber): Can swing outcome with reasonable probability  
- 1 (Yellow): Adds meaningful risk but unlikely decisive alone
- 0 (Grey): Not present/insufficient evidence

Respond in JSON format:
{{
    "detections": [
        {{
            "family_id": "F1",
            "pattern_id": "F1P1", 
            "severity": 2,
            "confidence": 0.8,
            "rationale": "Surrogate endpoint with no precedent in indication",
            "evidence_spans": [{{"doc_id": "123", "snippet_hash": "abc"}}]
        }}
    ]
}}

If no patterns detected for a family, omit it. Be conservative - only report patterns with strong evidence.
"""
        
        return prompt
    
    def _build_pattern_cards(self) -> str:
        """Build pattern cards for LLM prompt."""
        cards = []
        
        for pattern in self.patterns.values():
            card = f"""
{pattern['pattern_id']}: {pattern['name']}
Description: {pattern['description']}
Cue Phrases: {', '.join(pattern['cue_phrases'][:5])}  # Limit to 5 for brevity
Severity Rules: {pattern['severity_rules']}
"""
            cards.append(card)
        
        return "\n".join(cards)
    
    def _extract_text_slices(self, documents: List[Dict[str, Any]]) -> str:
        """Extract relevant text slices from documents."""
        slices = []
        
        for doc in documents[:3]:  # Limit to 3 documents for token management
            doc_text = doc.get('content', '')[:2000]  # Limit text length
            slices.append(f"Document {doc.get('doc_id', 'unknown')}:\n{doc_text}\n")
        
        return "\n".join(slices)
    
    def _parse_llm_response(self, response: Dict[str, Any]) -> List[PatternDetection]:
        """Parse LLM response into PatternDetection objects."""
        try:
            if 'detections' not in response:
                return []
            
            detections = []
            for detection_data in response['detections']:
                detection = PatternDetection(
                    family_id=detection_data['family_id'],
                    pattern_id=detection_data['pattern_id'],
                    severity=SeverityLevel(detection_data['severity']),
                    confidence=detection_data['confidence'],
                    rationale=detection_data['rationale'],
                    evidence_spans=detection_data.get('evidence_spans', [])
                )
                detections.append(detection)
            
            return detections
            
        except Exception as e:
            self.logger.error(f"Error parsing LLM response: {e}")
            return []
    
    def _apply_deterministic_guards(self, detections: List[PatternDetection], trial_context: Dict[str, Any]) -> List[PatternDetection]:
        """Apply deterministic guards to LLM detections."""
        
        # Example: Power calculation guard for F2P1
        if any(d.pattern_id == 'F2P1' for d in detections):
            # Recalculate power and adjust severity if needed
            power = self._calculate_power(trial_context)
            if power is not None:
                for detection in detections:
                    if detection.pattern_id == 'F2P1':
                        if power < 0.5:
                            detection.severity = SeverityLevel.RED
                        elif power < 0.8:
                            detection.severity = SeverityLevel.YELLOW
                        else:
                            detection.severity = SeverityLevel.GREY
        
        return detections
    
    def _calculate_power(self, trial_context: Dict[str, Any]) -> Optional[float]:
        """Calculate statistical power for F2P1 guard."""
        # TODO: Implement power calculation
        # This would use the same logic as the old S2 signal
        return None