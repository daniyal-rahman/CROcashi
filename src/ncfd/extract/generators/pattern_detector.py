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
        
        # Log initialization status
        self.logger.info(f"PatternFamilyDetector initialized with {len(self.patterns)} patterns from {self.config_path}")
        if not self.patterns:
            self.logger.warning("No patterns loaded - pattern detection will not work")
    
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
            detections = await self.detect_patterns(doc_id, [{"text": raw_doc_text, "doc_id": doc_id}], trial_context)
            
            self.logger.info(f"Generated {len(detections)} pattern detections for document {doc_id}")
            return {
                "pattern_detections": detections,
                "success": True,
                "error_message": None
            }
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Pattern detection failed: {error_msg}")
            
            # Check for the specific float subscriptable error
            if 'float' in error_msg and 'subscriptable' in error_msg:
                self.logger.error("🚨 Detected 'float' object is not subscriptable error!")
                self.logger.error("This indicates the LLM returned malformed JSON with numbers instead of detection objects.")
                self.logger.error("The LLM response likely contained something like: {'detections': [0.95, 0.87]} instead of proper detection objects.")
            
            return {
                "pattern_detections": [],
                "success": False,
                "error_message": error_msg
            }
    
    def _load_config(self) -> Dict[str, Any]:
        """Load Pattern Families configuration."""
        config_file = Path(self.config_path)
        if not config_file.exists():
            self.logger.error(f"Config file not found: {self.config_path}")
            return {}
        
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            self.logger.info(f"Successfully loaded config from {self.config_path}")
            return config
        except Exception as e:
            self.logger.error(f"Failed to load config from {self.config_path}: {e}")
            return {}
    
    def _load_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Load pattern configurations."""
        patterns = {}
        
        if 'families' not in self.config:
            self.logger.error("No 'families' section found in pattern_families.yaml config")
            return patterns
        
        # Log loaded patterns
        total_patterns = 0
        for family_id, family_data in self.config['families'].items():
            pattern_count = len(family_data.get('patterns', {}))
            total_patterns += pattern_count
            self.logger.info(f"Loaded {pattern_count} patterns for family {family_id}")
            
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
        
        self.logger.info(f"Total patterns loaded: {total_patterns}")
        return patterns
    
    async def detect_patterns(self, 
                            trial_id: str,
                            documents: List[Dict[str, Any]],
                            trial_context: Dict[str, Any]) -> List[PatternDetection]:
        """Detect patterns using LLM."""
        
        try:
            # Validate inputs
            if not documents:
                self.logger.warning("No documents provided for pattern detection")
                return []
            
            # Build prompt
            prompt = self._build_detection_prompt(documents, trial_context)
            self.logger.debug(f"Built prompt with {len(documents)} documents")
            
            # Call LLM
            response = await self._extract_with_llm("", trial_context, prompt)
            
            # Parse response
            detections = self._parse_llm_response(response)
            self.logger.info(f"Parsed {len(detections)} pattern detections from LLM response")
            
            # Apply deterministic guards
            detections = self._apply_deterministic_guards(detections, trial_context)
            
            return detections
            
        except Exception as e:
            self.logger.error(f"Pattern detection failed for trial {trial_id}: {e}")
            return []
    
    def _get_data_key(self) -> str:
        """Return the key for the main data in the LLM response."""
        return "pattern_detections"
    
    def _build_standard_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build the standard prompt for pattern detection."""
        documents = [{"text": doc_text, "doc_id": doc_id}]
        return self._build_detection_prompt(documents, trial_context)
    
    async def _extract_with_llm(self, doc_text: str, trial_context: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Extract data using LLM with the given prompt."""
        try:
            # Make LLM call with structured JSON schema
            json_schema = {
                "type": "object",
                "properties": {
                    "detections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "family_id": {"type": "string"},
                                "pattern_id": {"type": "string"},
                                "severity": {"type": "integer", "minimum": 1, "maximum": 3},
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                                "rationale": {"type": "string"},
                                "evidence_quotes": {"type": "array", "items": {"type": "string"}},
                                "doc_id": {"type": "string"}
                            },
                            "required": ["family_id", "pattern_id", "severity", "confidence", "rationale"]
                        }
                    }
                },
                "required": ["detections"]
            }
            
            response = await self.call_llm(
                messages=[prompt],
                temperature=0.1,
                max_tokens=2000,
                json_schema=json_schema
            )
            
            # Parse the response using robust JSON parsing
            result = response.content
            self.logger.debug(f"LLM raw response type: {type(result)}")
            self.logger.debug(f"LLM raw response content: {str(result)[:500]}...")
            
            if isinstance(result, str):
                # Use robust JSON parsing like other generators
                from ...llm.json_parser import parse_llm_json_response
                parsed_result = parse_llm_json_response(result, expected_fields=["detections"])
                if parsed_result:
                    result = parsed_result
                    self.logger.info(f"Successfully parsed LLM response with {len(result.get('detections', []))} detections")
                else:
                    self.logger.error(f"Failed to parse LLM response: {result}")
                    return {"detections": []}
            elif isinstance(result, (int, float)):
                self.logger.error(f"LLM returned a number ({result}) instead of JSON. This will cause parsing errors.")
                return {"detections": []}
            elif not isinstance(result, dict):
                self.logger.error(f"LLM returned unexpected type {type(result)}: {result}")
                return {"detections": []}
            
            return result
            
        except Exception as e:
            self.logger.error(f"LLM pattern detection failed: {e}")
            return {"detections": []}
    
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
- family_id (F1-F9) - MUST be string format like "F1", "F2", etc.
- pattern_id (F1P1-F9P4) - MUST be string format like "F1P1", "F2P1", etc.
- severity (0-3: Grey/Yellow/Amber/Red) - MUST be integer
- confidence (0-1) - MUST be float
- rationale (brief explanation) - MUST be string
- evidence_spans (doc_id + snippet_hash) - MUST be array

Severity Rubric:
- 3 (Red): Likely to materially invalidate result or approval path
- 2 (Amber): Can swing outcome with reasonable probability  
- 1 (Yellow): Adds meaningful risk but unlikely decisive alone
- 0 (Grey): Not present/insufficient evidence

IMPORTANT: Use exact string formats for family_id and pattern_id. Use integers for severity.

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
            # Try multiple field names for text content
            doc_text = (doc.get('text', '') or 
                       doc.get('content', '') or 
                       doc.get('fulltext_text', '') or 
                       doc.get('abstract_text', ''))[:2000]  # Limit text length
            
            if doc_text:
                slices.append(f"Document {doc.get('doc_id', 'unknown')}:\n{doc_text}\n")
            else:
                self.logger.warning(f"No text content found for document {doc.get('doc_id', 'unknown')}")
        
        return "\n".join(slices)
    
    def _parse_llm_response(self, response: Dict[str, Any]) -> List[PatternDetection]:
        """Parse LLM response into PatternDetection objects."""
        try:
            if 'detections' not in response:
                self.logger.warning("No 'detections' field found in LLM response")
                self.logger.debug(f"Response keys: {list(response.keys())}")
                return []
            
            detections = []
            detection_list = response['detections']
            
            if not isinstance(detection_list, list):
                self.logger.error(f"Expected 'detections' to be a list, got {type(detection_list)}")
                return []
            
            for i, detection_data in enumerate(detection_list):
                try:
                    # Validate that detection_data is a dictionary
                    if not isinstance(detection_data, dict):
                        self.logger.error(f"Detection {i} is not a dictionary, got {type(detection_data)}: {detection_data}")
                        self.logger.error(f"This indicates the LLM returned malformed JSON. Expected detection objects but got {type(detection_data)} values.")
                        continue
                    
                    # Validate required fields
                    required_fields = ['family_id', 'pattern_id', 'severity', 'confidence', 'rationale']
                    missing_fields = [field for field in required_fields if field not in detection_data]
                    if missing_fields:
                        self.logger.warning(f"Detection {i} missing fields: {missing_fields}")
                        continue
                    
                    # Normalize family_id and pattern_id to string format
                    family_id = str(detection_data['family_id']).replace('.0', '')
                    pattern_id = str(detection_data['pattern_id']).replace('.0', '')
                    
                    # Convert numeric family/pattern IDs to proper format
                    if family_id.isdigit():
                        family_id = f"F{family_id}"
                    if pattern_id.isdigit():
                        pattern_id = f"{family_id}P{pattern_id}"
                    
                    # Update detection_data with normalized values
                    detection_data['family_id'] = family_id
                    detection_data['pattern_id'] = pattern_id
                    
                    # Validate severity value (allow 0-3 as per SeverityLevel enum)
                    severity_value = detection_data['severity']
                    if not isinstance(severity_value, int) or severity_value < 0 or severity_value > 3:
                        self.logger.warning(f"Invalid severity value {severity_value} for detection {i}")
                        continue
                    
                    # Validate confidence value
                    confidence_value = detection_data['confidence']
                    if not isinstance(confidence_value, (int, float)) or confidence_value < 0 or confidence_value > 1:
                        self.logger.warning(f"Invalid confidence value {confidence_value} for detection {i}")
                        continue
                    
                    detection = PatternDetection(
                        family_id=detection_data['family_id'],
                        pattern_id=detection_data['pattern_id'],
                        severity=SeverityLevel(severity_value),
                        confidence=float(confidence_value),
                        rationale=detection_data['rationale'],
                        evidence_spans=detection_data.get('evidence_spans', [])
                    )
                    detections.append(detection)
                    
                except Exception as e:
                    self.logger.error(f"Error parsing detection {i}: {e}")
                    continue
            
            self.logger.info(f"Successfully parsed {len(detections)} valid pattern detections")
            return detections
            
        except Exception as e:
            self.logger.error(f"Error parsing LLM response: {e}")
            self.logger.debug(f"Response content: {response}")
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
        """
        Calculate statistical power for F2P1 guard.
        
        Note: This is a placeholder implementation. Statistical power calculation
        would require trial design parameters (sample size, effect size, alpha level)
        that are not currently available in the trial context.
        
        Args:
            trial_context: Trial context information
            
        Returns:
            Statistical power (0-1) or None if calculation not possible
        """
        # Placeholder implementation - would require trial design parameters
        return None