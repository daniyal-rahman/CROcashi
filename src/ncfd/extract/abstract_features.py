"""
Abstract features extraction for clinical trial literature.

Uses regex patterns and heuristics to extract structured data from PubMed abstracts.
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    """Represents an extracted entity from text."""
    ent_type: str
    value_text: str
    value_norm: str
    char_start: int
    char_end: int
    confidence: float
    detector: str
    metadata: Optional[Dict[str, Any]] = None


class AbstractFeatureExtractor:
    """Extracts clinical trial features from PubMed abstracts."""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize feature extractor.
        
        Args:
            config: Configuration dictionary with extraction parameters
        """
        self.config = config or {}
        
        # Compile regex patterns for performance
        self.patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Compile all regex patterns."""
        patterns = {
            # Clinical trial identifiers
            'nct_id': re.compile(r'\bNCT\d{8}\b', re.IGNORECASE),
            
            # Trial phases - fixed to catch all phases and support multiple formats
            'phase': re.compile(r'\b(?:phase\s*)?([IViv12]+(?:/[23])?)\s*(?:trial|study|clinical)?', re.IGNORECASE),
            
            # Sample sizes
            'n_total': re.compile(r'\b(\d+(?:,\d+)*)\s*(?:patients?|subjects?|participants?|individuals?)', re.IGNORECASE),
            
            # Primary endpoints
            'endpoint': re.compile(r'\b(?:primary\s+)?(?:endpoint|outcome|objective)\s*:?\s*([^\.]+)', re.IGNORECASE),
            
            # Effect sizes and statistics
            'effect_size': re.compile(r'\b(?:HR|hazard\s+ratio|OR|odds\s+ratio|RR|risk\s+ratio)\s*[=:]\s*([0-9.]+)', re.IGNORECASE),
            'p_value': re.compile(r'\bp\s*[=:<>]\s*([0-9.]+)', re.IGNORECASE),
            'ci': re.compile(r'\b(?:95%?\s*)?CI\s*[=:]\s*([0-9.]+\s*[-–]\s*[0-9.]+)', re.IGNORECASE),
            
            # Risk signals - improved with negation context
            'risk_signal': re.compile(r'(?:did\s+not\s+meet|failed|futility|non.?inferiority\s+not\s+demonstrated|trend\s+only|post.?hoc|subgroup|interim)', re.IGNORECASE),
            
            # Safety signals - improved with negation context
            'safety_signal': re.compile(r'(?:discontinuation|adverse\s+event|toxicity|side\s+effect|safety|tolerability)', re.IGNORECASE),
            
            # Study design
            'design': re.compile(r'\b(?:randomized|controlled|double.?blind|single.?blind|placebo.?controlled|open.?label|crossover|parallel|sequential)', re.IGNORECASE),
            
            # Control type
            'control_type': re.compile(r'\b(?:placebo|standard\s+of\s+care|active\s+control|historical\s+control|no\s+control)', re.IGNORECASE),
            
            # Population/subgroup
            'population': re.compile(r'\b(?:adult|pediatric|elderly|geriatric|biomarker|mutation|wild.?type|refractory|relapsed|metastatic)', re.IGNORECASE),
            
            # Asset names (drugs) - expanded to catch more patterns
            'asset_name': re.compile(r'\b([A-Z][a-z]+(?:-[A-Z][a-z]+)*\s+(?:hydrochloride|sulfate|citrate|phosphate|acetate|sodium|potassium|mab|cept|tinib|ciclib|nib|parib|inib|zomib|mide|afil|pril|sartan|statin|prazole|oxacin|mycin|vir|rel|umab|zumab|ximab|omab))\b'),
            
            # MOA (mechanism of action)
            'moa': re.compile(r'\b(?:inhibitor|agonist|antagonist|antibody|vaccine|gene\s+therapy|cell\s+therapy)\b', re.IGNORECASE),
        }
        
        return patterns
    
    def extract_all_features(self, text: str) -> List[ExtractedEntity]:
        """
        Extract all features from text.
        
        Args:
            text: Text to extract features from
            
        Returns:
            List of extracted entities
        """
        if not text:
            return []
        
        entities = []
        
        # Extract each type of entity
        for ent_type, pattern in self.patterns.items():
            try:
                extracted = self._extract_entity_type(text, ent_type, pattern)
                entities.extend(extracted)
            except Exception as e:
                logger.warning(f"Failed to extract {ent_type}: {e}")
                continue
        
        # Remove overlapping entities (keep the one with higher confidence)
        entities = self._remove_overlaps(entities)
        
        return entities
    
    def _extract_entity_type(self, text: str, ent_type: str, pattern: re.Pattern) -> List[ExtractedEntity]:
        """Extract entities of a specific type."""
        entities = []
        
        for match in pattern.finditer(text):
            value_text = match.group(0)
            value_norm = self._normalize_value(ent_type, value_text)
            
            # Check for negation context for risk and safety signals
            if ent_type in ['risk_signal', 'safety_signal']:
                if self._is_negated_context(text, match.start(), match.end(), value_text):
                    continue  # Skip negated signals
            
            # Calculate confidence based on entity type and context
            confidence = self._calculate_confidence(ent_type, value_text, match.start(), match.end(), text)
            
            entity = ExtractedEntity(
                ent_type=ent_type,
                value_text=value_text,
                value_norm=value_norm,
                char_start=match.start(),
                char_end=match.end(),
                confidence=confidence,
                detector='regex',
                metadata=self._extract_metadata(ent_type, match, text)
            )
            
            entities.append(entity)
        
        return entities
    
    def _is_negated_context(self, text: str, start: int, end: int, entity_text: str) -> bool:
        """Check if entity appears in a negated context."""
        # Look for negation words within a smaller context window
        context_start = max(0, start - 50)
        context_end = min(len(text), end + 50)
        context = text[context_start:context_end].lower()
        
        # Common negation words and phrases - more specific
        negations = [
            'no ', 'not ', 'none ', 'neither ', 'nor ', 'never ', 'nobody ', 'nothing ',
            'nowhere ', 'hardly ', 'barely ', 'scarcely ', 'seldom ', 'rarely ',
            'unlikely ', 'impossible ', 'did not ', 'was not ',
            'were not ', 'is not ', 'are not ', 'has not ', 'have not ',
            'without ', 'lack of ', 'absence of ', 'free from '
        ]
        
        # Check if any negation word appears in context
        for neg in negations:
            if neg in context:
                # Check if negation is close to the entity (within ~5 words)
                entity_pos = start - context_start
                neg_pos = context.find(neg)
                if abs(entity_pos - neg_pos) < 30:  # Within 30 characters (~5 words)
                    return True
        
        # Check for specific negative patterns around the entity
        entity_lower = entity_text.lower()
        if 'failed' in entity_lower:
            # Check if "failed" is actually about something else
            if 'failed to enroll' in context or 'failed to recruit' in context:
                return True
        elif 'safety' in entity_lower:
            # Check if safety is mentioned positively
            positive_safety = ['safety profile', 'safety data', 'safety analysis', 'safety assessment']
            if any(phrase in context for phrase in positive_safety):
                return True
        
        return False
    
    def _normalize_value(self, ent_type: str, value: str) -> str:
        """Normalize extracted value based on entity type."""
        normalized = value.strip()
        
        if ent_type == 'nct_id':
            return normalized.upper()
        elif ent_type == 'phase':
            # Normalize phase to standard format
            phase_match = re.search(r'([IViv12]+(?:/[23])?)', normalized, re.IGNORECASE)
            if phase_match:
                phase = phase_match.group(1).upper()
                # Convert roman numerals to numbers
                roman_to_arabic = {
                    'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
                    'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5'
                }
                
                if phase in roman_to_arabic:
                    return f"PHASE{roman_to_arabic[phase]}"
                elif phase in ['1', '2', '3', '4', '5']:
                    return f"PHASE{phase}"
                elif '/' in phase:  # Handle "2/3" format
                    parts = phase.split('/')
                    if len(parts) == 2 and parts[0] in ['2', '3'] and parts[1] in ['2', '3']:
                        # For 2/3, use the higher phase (more relevant)
                        return f"PHASE{max(int(parts[0]), int(parts[1]))}"
                
                # Fallback for unrecognized formats
                return f"PHASE{phase}"
        elif ent_type == 'n_total':
            # Remove commas and convert to number
            return re.sub(r'[^\d]', '', normalized)
        elif ent_type == 'p_value':
            # Normalize p-value format
            return re.sub(r'[^\d.]', '', normalized)
        elif ent_type == 'effect_size':
            # Extract just the numeric value
            num_match = re.search(r'([0-9.]+)', normalized)
            if num_match:
                return num_match.group(1)
        
        return normalized.lower()
    
    def _calculate_confidence(self, ent_type: str, value: str, start: int, end: int, text: str) -> float:
        """Calculate confidence score for extracted entity."""
        base_confidence = 0.7
        
        # Adjust based on entity type
        if ent_type == 'nct_id':
            base_confidence = 0.95  # NCT IDs are very reliable
        elif ent_type == 'phase':
            base_confidence = 0.85  # Phase information is usually reliable
        elif ent_type == 'n_total':
            base_confidence = 0.80  # Sample sizes are usually reliable
        elif ent_type == 'p_value':
            base_confidence = 0.75  # P-values can have various formats
        elif ent_type == 'effect_size':
            base_confidence = 0.70  # Effect sizes can be complex
        
        # Adjust based on context
        context_bonus = self._get_context_bonus(text, start, end)
        
        # Adjust based on value quality
        quality_bonus = self._get_quality_bonus(ent_type, value)
        
        confidence = base_confidence + context_bonus + quality_bonus
        return min(max(confidence, 0.0), 1.0)  # Clamp to [0, 1]
    
    def _get_context_bonus(self, text: str, start: int, end: int) -> float:
        """Get confidence bonus based on surrounding context."""
        bonus = 0.0
        
        # Check if entity is in a sentence with clinical trial keywords
        sentence_start = max(0, start - 100)
        sentence_end = min(len(text), end + 100)
        context = text[sentence_start:sentence_end].lower()
        
        clinical_keywords = ['trial', 'study', 'clinical', 'patient', 'treatment', 'therapy']
        if any(keyword in context for keyword in clinical_keywords):
            bonus += 0.1
        
        # Check if entity is near numbers (good context)
        if re.search(r'\d+', context):
            bonus += 0.05
        
        return bonus
    
    def _get_quality_bonus(self, ent_type: str, value: str) -> float:
        """Get confidence bonus based on value quality."""
        bonus = 0.0
        
        if ent_type == 'nct_id':
            # NCT IDs should be exactly 11 characters
            if len(value) == 11:
                bonus += 0.1
        elif ent_type == 'phase':
            # Phase should be recognizable
            if re.match(r'^[IViv12]+$', value, re.IGNORECASE):
                bonus += 0.1
        elif ent_type == 'n_total':
            # Sample size should be reasonable
            try:
                n = int(re.sub(r'[^\d]', '', value))
                if 10 <= n <= 100000:  # Reasonable range
                    bonus += 0.1
            except ValueError:
                pass
        elif ent_type == 'p_value':
            # P-value should be between 0 and 1
            try:
                p = float(re.sub(r'[^\d.]', '', value))
                if 0.0 <= p <= 1.0:
                    bonus += 0.1
            except ValueError:
                pass
        
        return bonus
    
    def _extract_metadata(self, ent_type: str, match: re.Match, text: str) -> Dict[str, Any]:
        """Extract additional metadata for entity."""
        metadata = {}
        
        if ent_type == 'nct_id':
            # Extract surrounding context for NCT ID
            context_start = max(0, match.start() - 50)
            context_end = min(len(text), match.end() + 50)
            metadata['context'] = text[context_start:context_end]
            
        elif ent_type == 'phase':
            # Extract the phase number/letter
            phase_match = re.search(r'([IViv12]+(?:/[23])?)', match.group(0), re.IGNORECASE)
            if phase_match:
                metadata['phase_value'] = phase_match.group(1).upper()
                
        elif ent_type == 'n_total':
            # Extract the numeric value
            num_match = re.search(r'(\d+(?:,\d+)*)', match.group(0))
            if num_match:
                metadata['numeric_value'] = int(num_match.group(1).replace(',', ''))
                
        elif ent_type == 'effect_size':
            # Extract the type of effect size
            if 'HR' in match.group(0) or 'hazard' in match.group(0):
                metadata['effect_type'] = 'hazard_ratio'
            elif 'OR' in match.group(0) or 'odds' in match.group(0):
                metadata['effect_type'] = 'odds_ratio'
            elif 'RR' in match.group(0) or 'risk' in match.group(0):
                metadata['effect_type'] = 'risk_ratio'
                
        elif ent_type == 'p_value':
            # Extract the comparison operator
            op_match = re.search(r'([=<>])', match.group(0))
            if op_match:
                metadata['comparison'] = op_match.group(1)
        
        elif ent_type == 'ci':
            # Check if CI crosses null value (1.0 for ratios)
            ci_text = match.group(1)
            try:
                # Extract numeric bounds
                bounds = re.findall(r'([0-9.]+)', ci_text)
                if len(bounds) >= 2:
                    lower = float(bounds[0])
                    upper = float(bounds[1])
                    metadata['lower_bound'] = lower
                    metadata['upper_bound'] = upper
                    metadata['crosses_null'] = lower <= 1.0 <= upper
                    metadata['width'] = upper - lower
            except (ValueError, IndexError):
                pass
        
        return metadata
    
    def _remove_overlaps(self, entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
        """Remove overlapping entities, keeping the one with higher confidence within each entity type."""
        if not entities:
            return entities
        
        # Group entities by type
        entities_by_type = {}
        for entity in entities:
            ent_type = entity.ent_type
            if ent_type not in entities_by_type:
                entities_by_type[ent_type] = []
            entities_by_type[ent_type].append(entity)
        
        # Remove overlaps within each type separately
        filtered = []
        for ent_type, type_entities in entities_by_type.items():
            # Sort by confidence (descending) and start position
            type_entities.sort(key=lambda x: (-x.confidence, x.char_start))
            
            type_filtered = []
            for entity in type_entities:
                # Check if this entity overlaps with any already accepted within this type
                overlaps = False
                for accepted in type_filtered:
                    if self._entities_overlap(entity, accepted):
                        overlaps = True
                        break
                
                if not overlaps:
                    type_filtered.append(entity)
            
            filtered.extend(type_filtered)
        
        return filtered
    
    def _entities_overlap(self, ent1: ExtractedEntity, ent2: ExtractedEntity) -> bool:
        """Check if two entities overlap in text."""
        return not (ent1.char_end <= ent2.char_start or ent2.char_end <= ent1.char_start)
    
    def extract_nct_ids(self, text: str, entities: Optional[List[ExtractedEntity]] = None) -> List[str]:
        """Extract NCT IDs from text."""
        if entities is None:
            entities = self.extract_all_features(text)
        nct_entities = [e for e in entities if e.ent_type == 'nct_id']
        return [e.value_norm for e in nct_entities]
    
    def extract_phases(self, text: str, entities: Optional[List[ExtractedEntity]] = None) -> List[str]:
        """Extract trial phases from text."""
        if entities is None:
            entities = self.extract_all_features(text)
        phase_entities = [e for e in entities if e.ent_type == 'phase']
        return [e.value_norm for e in phase_entities]
    
    def extract_sample_sizes(self, text: str, entities: Optional[List[ExtractedEntity]] = None) -> List[int]:
        """Extract sample sizes from text."""
        if entities is None:
            entities = self.extract_all_features(text)
        n_entities = [e for e in entities if e.ent_type == 'n_total']
        sizes = []
        for entity in n_entities:
            try:
                size = int(entity.value_norm)
                sizes.append(size)
            except ValueError:
                continue
        return sizes
    
    def extract_risk_signals(self, text: str, entities: Optional[List[ExtractedEntity]] = None) -> List[str]:
        """Extract risk signal phrases from text."""
        if entities is None:
            entities = self.extract_all_features(text)
        risk_entities = [e for e in entities if e.ent_type == 'risk_signal']
        return [e.value_text.lower() for e in risk_entities]
    
    def extract_safety_signals(self, text: str, entities: Optional[List[ExtractedEntity]] = None) -> List[str]:
        """Extract safety signal phrases from text."""
        if entities is None:
            entities = self.extract_all_features(text)
        safety_entities = [e for e in entities if e.ent_type == 'safety_signal']
        return [e.value_text.lower() for e in safety_entities]
    
    def get_extraction_stats(self, entities: List[ExtractedEntity]) -> Dict[str, Any]:
        """Get statistics about extracted entities."""
        if not entities:
            return {}
        
        # Count by entity type
        type_counts = {}
        for entity in entities:
            ent_type = entity.ent_type
            type_counts[ent_type] = type_counts.get(ent_type, 0) + 1
        
        # Confidence statistics
        confidences = [e.confidence for e in entities]
        
        return {
            'total_entities': len(entities),
            'entity_types': type_counts,
            'avg_confidence': sum(confidences) / len(confidences) if confidences else 0,
            'min_confidence': min(confidences) if confidences else 0,
            'max_confidence': max(confidences) if confidences else 0,
            'high_confidence_count': len([c for c in confidences if c >= 0.8]),
            'medium_confidence_count': len([c for c in confidences if 0.5 <= c < 0.8]),
            'low_confidence_count': len([c for c in confidences if c < 0.5])
        }
