"""
Analysis Claim Extractor for Subgroup/Endpoint Detection.

This module extracts structured analysis claims from text to support S3/G2 signal detection.
"""

import re
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RegexHints:
    """Hints extracted from regex patterns."""
    p_values: List[str]
    nominal_phrases: List[str]
    post_hoc_phrases: List[str]
    subgroup_cues: List[str]
    analysis_sets: List[str]
    interaction_tests: List[str]
    multiplicity_methods: List[str]


class AnalysisClaimExtractor:
    """
    Extracts structured analysis claims from text using regex hints + LLM.
    
    This extractor identifies subgroup-only wins, endpoint changes, and analysis gaming patterns
    to support S3 (subgroup-only wins) and G2 (analysis gaming) signal detection.
    """
    
    def __init__(self):
        """Initialize the extractor with regex patterns."""
        self.patterns = {
            'p_values': re.compile(r'p\s*=?\s*(?:<|≤|=)\s*0\.\d{1,3}', re.IGNORECASE),
            'nominal': re.compile(r'nominal(ly)?\s*(significant|p)', re.IGNORECASE),
            'post_hoc': re.compile(r'post-?hoc|explorator(y|ies)', re.IGNORECASE),
            'subgroup_cues': re.compile(r'(mild|moderate|severe)\b|MMSE\s*[≥≤]\s*\d+|APOE|ε4|age\s*[<>]=?\s*\d+', re.IGNORECASE),
            'analysis_sets': re.compile(r'per-?protocol|completer|open-?label|ITT|mITT', re.IGNORECASE),
            'interaction': re.compile(r'interaction\s*p\s*=?\s*0\.\d+', re.IGNORECASE),
            'multiplicity': re.compile(r'multiplicity|Hochberg|Holm|Bonferroni|FDR', re.IGNORECASE)
        }
    
    def extract_regex_hints(self, text: str) -> RegexHints:
        """Extract hints using regex patterns."""
        hints = RegexHints(
            p_values=[match.group() for match in self.patterns['p_values'].finditer(text)],
            nominal_phrases=[match.group() for match in self.patterns['nominal'].finditer(text)],
            post_hoc_phrases=[match.group() for match in self.patterns['post_hoc'].finditer(text)],
            subgroup_cues=[match.group() for match in self.patterns['subgroup_cues'].finditer(text)],
            analysis_sets=[match.group() for match in self.patterns['analysis_sets'].finditer(text)],
            interaction_tests=[match.group() for match in self.patterns['interaction'].finditer(text)],
            multiplicity_methods=[match.group() for match in self.patterns['multiplicity'].finditer(text)]
        )
        
        logger.debug(f"Extracted regex hints: {hints}")
        return hints
    
    def build_extraction_prompt(self, text: str, hints: RegexHints, doc_id: str) -> str:
        """Build LLM prompt for analysis claim extraction."""
        
        hints_text = ""
        if hints.p_values:
            hints_text += f"P-values found: {', '.join(hints.p_values)}\n"
        if hints.nominal_phrases:
            hints_text += f"Nominal phrases: {', '.join(hints.nominal_phrases)}\n"
        if hints.post_hoc_phrases:
            hints_text += f"Post-hoc phrases: {', '.join(hints.post_hoc_phrases)}\n"
        if hints.subgroup_cues:
            hints_text += f"Subgroup cues: {', '.join(hints.subgroup_cues)}\n"
        if hints.analysis_sets:
            hints_text += f"Analysis sets: {', '.join(hints.analysis_sets)}\n"
        if hints.interaction_tests:
            hints_text += f"Interaction tests: {', '.join(hints.interaction_tests)}\n"
        if hints.multiplicity_methods:
            hints_text += f"Multiplicity methods: {', '.join(hints.multiplicity_methods)}\n"
        
        prompt = f"""You are a clinical trial analysis expert. Extract analysis claims from this document.

DOCUMENT ID: {doc_id}

REGEX HINTS FOUND:
{hints_text}

TEXT TO ANALYZE:
{text[:4000]}...

Extract analysis claims following this JSON schema. Return ONLY valid JSON:

{{
  "analysis_claims": [
    {{
      "trial_id": "string",
      "source_id": "doc_{doc_id}",
      "analysis_set": "ITT | mITT | PP | Completers | Open-label",
      "endpoint": "string",
      "overall_result": {{
        "effect": "NS | FavoursTx | FavoursCtrl | N/A",
        "p_value": 0.23,
        "adjusted": true,
        "multiplicity_method": "Hochberg | Bonferroni | None | Unknown"
      }},
      "subgroup": {{
        "label": "Mild AD (MMSE ≥ 20)",
        "type": "disease_severity | genotype | geography | age | sex | site | compliance",
        "prespecified": false,
        "size_n_treatment": 84,
        "size_n_control": 88
      }},
      "subgroup_result": {{
        "effect": "FavoursTx | FavoursCtrl | NS",
        "delta": -2.3,
        "unit": "ADAS points",
        "p_value": 0.041,
        "adjusted": false,
        "is_nominal": true,
        "interaction_p": 0.29
      }},
      "claims_language": ["post-hoc", "nominal p", "exploratory"],
      "evidence_strength": "regulatory | peer_review | conf_poster | company",
      "quote_spans": [
        {{"text": "exact quote from text", "page": 12}}
      ]
    }}
  ]
}}

RULES:
1. Only extract claims where overall result is NS/no-control AND subgroup shows positive effect
2. Set adjusted=false and is_nominal=true when "nominal" appears in text
3. Set prespecified=false when "post-hoc" or "exploratory" appears
4. Include exact quotes that support each claim
5. If no subgroup-only patterns found, return {{"analysis_claims": []}}"""

        return prompt
    
    async def extract_claims(self, text: str, doc_id: str) -> List[Dict[str, Any]]:
        """
        Extract analysis claims from text.
        
        Args:
            text: Document text to analyze
            doc_id: Document identifier
            
        Returns:
            List of analysis claim dictionaries
        """
        try:
            # Step 1: Extract regex hints
            hints = self.extract_regex_hints(text)
            
            # Step 2: Build LLM prompt
            prompt = self.build_extraction_prompt(text, hints, doc_id)
            
            # Step 3: Call LLM (placeholder - will be implemented with actual LLM call)
            # For now, return empty list
            logger.info(f"Analysis claim extraction requested for doc_id={doc_id}")
            logger.debug(f"Regex hints found: {len(hints.p_values)} p-values, {len(hints.subgroup_cues)} subgroup cues")
            
            # Make LLM call for analysis claim extraction
            from ncfd.llm.base_worker import LLMWorker
            from ncfd.llm.base_provider import get_provider
            
            # Create LLM worker for analysis claim extraction
            provider = get_provider()
            worker = LLMWorker(provider=provider)
            
            response = await worker.call_llm(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4000,
                json_output=True
            )
            
            # Parse LLM response
            claims = self._parse_llm_response(response.content)
            return self._normalize_claims(claims)
            
        except Exception as e:
            logger.error(f"Error extracting analysis claims for doc_id={doc_id}: {e}")
            return []
    
    def _parse_llm_response(self, response_content: str) -> List[Dict[str, Any]]:
        """Parse LLM response to extract analysis claims."""
        try:
            import json
            
            if isinstance(response_content, str):
                parsed = json.loads(response_content)
            else:
                parsed = response_content
            
            # Extract analysis claims from response
            if isinstance(parsed, dict) and 'analysis_claims' in parsed:
                return parsed['analysis_claims']
            elif isinstance(parsed, list):
                return parsed
            else:
                logger.warning(f"Unexpected LLM response format: {type(parsed)}")
                return []
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return []
    
    def _normalize_claims(self, claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize and validate extracted claims."""
        normalized = []
        
        for claim in claims:
            try:
                # Normalize subgroup labels
                subgroup_label = claim.get('subgroup', {}).get('label', '')
                if 'mild' in subgroup_label.lower():
                    claim['subgroup']['type'] = 'disease_severity'
                
                # Normalize analysis sets
                analysis_set = claim.get('analysis_set', '').upper()
                if 'PER-PROTOCOL' in analysis_set or 'PP' in analysis_set:
                    claim['analysis_set'] = 'PP'
                elif 'COMPLETER' in analysis_set:
                    claim['analysis_set'] = 'Completers'
                elif 'OPEN-LABEL' in analysis_set or 'OL' in analysis_set:
                    claim['analysis_set'] = 'Open-label'
                elif 'ITT' in analysis_set:
                    claim['analysis_set'] = 'ITT'
                
                # Set nominal flags
                claims_language = claim.get('claims_language', [])
                if any('nominal' in lang.lower() for lang in claims_language):
                    claim['subgroup_result']['adjusted'] = False
                    claim['subgroup_result']['is_nominal'] = True
                
                # Set prespecified flags
                if any('post-hoc' in lang.lower() or 'exploratory' in lang.lower() for lang in claims_language):
                    claim['subgroup']['prespecified'] = False
                
                normalized.append(claim)
                
            except Exception as e:
                logger.warning(f"Error normalizing claim: {e}")
                continue
        
        return normalized
