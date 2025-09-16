"""
Clean Pattern Families Detector

Simple, elegant LLM-driven pattern detection for F1-F9 families.
No legacy code, no complexity - just clean pattern detection.
"""

import yaml
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from .models import PatternDetection, SeverityLevel

@dataclass
class PatternConfig:
    """Configuration for a single pattern."""
    family_id: str
    pattern_id: str
    name: str
    description: str
    cue_phrases: List[str]
    severity_rules: Dict[str, int]

class PatternFamilyDetector:
    """Clean, simple Pattern Families detector."""
    
    def __init__(self, config_path: str = "config/pattern_families.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.patterns = self._load_patterns()
        self.llm_client = self._init_llm_client()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load Pattern Families configuration."""
        config_file = Path(self.config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def _load_patterns(self) -> Dict[str, PatternConfig]:
        """Load pattern configurations."""
        patterns = {}
        
        for family_id, family_data in self.config['families'].items():
            for pattern_id, pattern_data in family_data['patterns'].items():
                full_pattern_id = f"{family_id}{pattern_id}"
                patterns[full_pattern_id] = PatternConfig(
                    family_id=family_id,
                    pattern_id=full_pattern_id,
                    name=pattern_data['name'],
                    description=pattern_data['description'],
                    cue_phrases=pattern_data['cue_phrases'],
                    severity_rules=pattern_data['severity_rules']
                )
        
        return patterns
    
    def _init_llm_client(self):
        """Initialize LLM client."""
        # TODO: Implement actual LLM client
        # For now, return a mock client
        return MockLLMClient()
    
    async def detect_patterns(self, 
                            trial_id: str,
                            documents: List[Dict[str, Any]],
                            trial_context: Dict[str, Any]) -> List[PatternDetection]:
        """Detect patterns using LLM."""
        
        # Build prompt
        prompt = self._build_detection_prompt(documents, trial_context)
        
        # Call LLM
        response = await self.llm_client.generate(prompt)
        
        # Parse response
        detections = self._parse_llm_response(response)
        
        # Apply deterministic guards
        detections = self._apply_deterministic_guards(detections, trial_context)
        
        return detections
    
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
{pattern.pattern_id}: {pattern.name}
Description: {pattern.description}
Cue Phrases: {', '.join(pattern.cue_phrases[:5])}  # Limit to 5 for brevity
Severity Rules: {pattern.severity_rules}
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
    
    def _parse_llm_response(self, response: str) -> List[PatternDetection]:
        """Parse LLM response into PatternDetection objects."""
        try:
            data = json.loads(response)
            detections = []
            
            for detection_data in data.get('detections', []):
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
            print(f"Error parsing LLM response: {e}")
            return []
    
    def _apply_deterministic_guards(self, detections: List[PatternDetection], trial_context: Dict[str, Any]) -> List[PatternDetection]:
        """Apply deterministic guards to LLM detections."""
        
        # Example: Power calculation guard
        if any(d.pattern_id == 'F2P1' for d in detections):
            # Recalculate power and adjust severity if needed
            power = self._calculate_power(trial_context)
            if power is not None:
                for detection in detections:
                    if detection.pattern_id == 'F2P1':
                        if power < 0.5:
                            detection.severity = SeverityLevel.RED
                        elif power < 0.7:
                            detection.severity = SeverityLevel.AMBER
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

class MockLLMClient:
    """Mock LLM client for testing."""
    
    async def generate(self, prompt: str) -> str:
        """Mock LLM generation."""
        # Return mock response
        return json.dumps({
            "detections": [
                {
                    "family_id": "F1",
                    "pattern_id": "F1P1",
                    "severity": 2,
                    "confidence": 0.8,
                    "rationale": "Mock detection for testing",
                    "evidence_spans": [{"doc_id": "123", "snippet_hash": "abc"}]
                }
            ]
        })
