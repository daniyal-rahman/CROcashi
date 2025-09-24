"""
Pattern Detection Service for Study Card Pipeline.

Handles pattern family detection from extracted study cards and factsheets.
This service extracts the pattern detection logic from the main pipeline.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ncfd.extract.generators import PatternFamilyDetector

logger = logging.getLogger(__name__)


@dataclass
class PatternDetectionResult:
    """Result of pattern detection."""
    detected_patterns: List[Dict[str, Any]]
    total_items_processed: int
    successful_detections: int
    failed_detections: int
    detection_errors: List[str]


class PatternDetectionService:
    """
    Service for detecting pattern families from extracted content.
    
    This service handles:
    - Pattern family detection from study cards and factsheets
    - Batch processing of extracted content
    - Error handling and retry logic
    - Result validation and formatting
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the pattern detection service.
        
        Args:
            config: Configuration dictionary with detection settings
        """
        self.config = config
        self.detection_config = config.get('pattern_detection', {})
        
        # Initialize pattern detector with error handling
        try:
            self.pattern_detector = PatternFamilyDetector()
            if not hasattr(self.pattern_detector, 'patterns'):
                logger.error("Pattern detector failed to initialize - patterns attribute missing")
                self.pattern_detector = None
        except Exception as e:
            logger.error(f"Failed to initialize pattern detector: {e}")
            self.pattern_detector = None
        
        # Configuration values
        self.batch_size = self.detection_config.get('batch_size', 10)
        self.max_retries = self.detection_config.get('max_retries', 3)
        self.timeout_seconds = self.detection_config.get('timeout_seconds', 300)
    
    async def detect_patterns(
        self, 
        study_cards: List[Dict[str, Any]], 
        factsheets: List[Dict[str, Any]],
        trial_id: str
    ) -> PatternDetectionResult:
        """
        Detect pattern families from study cards and factsheets.
        
        Args:
            study_cards: List of extracted study cards
            factsheets: List of extracted factsheets
            trial_id: Trial ID for context
            
        Returns:
            PatternDetectionResult with detected patterns
        """
        logger.info(f"🔍 Starting pattern detection for trial {trial_id}: {len(study_cards)} study cards, {len(factsheets)} factsheets")
        
        # Combine all content for pattern detection
        all_content = []
        all_content.extend(study_cards)
        all_content.extend(factsheets)
        
        if not all_content:
            logger.warning(f"⚠️ No content available for pattern detection in trial {trial_id}")
            return PatternDetectionResult(
                detected_patterns=[],
                total_items_processed=0,
                successful_detections=0,
                failed_detections=0,
                detection_errors=[]
            )
        
        detected_patterns = []
        detection_errors = []
        successful_detections = 0
        failed_detections = 0
        
        # Process content in batches
        for i in range(0, len(all_content), self.batch_size):
            batch = all_content[i:i + self.batch_size]
            logger.info(f"📦 Processing pattern detection batch {i//self.batch_size + 1}/{len(all_content)//self.batch_size + 1} with {len(batch)} items")
            
            # Process batch
            batch_result = await self._process_batch(batch, trial_id)
            
            # Collect results
            detected_patterns.extend(batch_result['patterns'])
            detection_errors.extend(batch_result['errors'])
            successful_detections += batch_result['successful']
            failed_detections += batch_result['failed']
        
        logger.info(f"✅ Pattern detection completed for trial {trial_id}: {successful_detections} successful, {failed_detections} failed, {len(detected_patterns)} total patterns")
        
        return PatternDetectionResult(
            detected_patterns=detected_patterns,
            total_items_processed=len(all_content),
            successful_detections=successful_detections,
            failed_detections=failed_detections,
            detection_errors=detection_errors
        )
    
    async def _process_batch(
        self, 
        content_items: List[Dict[str, Any]], 
        trial_id: str
    ) -> Dict[str, Any]:
        """Process a batch of content items for pattern detection."""
        patterns = []
        errors = []
        successful = 0
        failed = 0
        
        for item in content_items:
            try:
                # Detect patterns from content item
                item_patterns = await self._detect_patterns_from_item(item, trial_id)
                
                if item_patterns:
                    patterns.extend(item_patterns)
                    successful += 1
                else:
                    failed += 1
                    errors.append(f"No patterns detected in item {item.get('document_id', 'unknown')}")
                    
            except Exception as e:
                failed += 1
                error_msg = f"Error detecting patterns in item {item.get('document_id', 'unknown')}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return {
            'patterns': patterns,
            'errors': errors,
            'successful': successful,
            'failed': failed
        }
    
    async def _detect_patterns_from_item(
        self, 
        content_item: Dict[str, Any], 
        trial_id: str
    ) -> List[Dict[str, Any]]:
        """Detect patterns from a single content item."""
        try:
            # Prepare content for pattern detection
            content_text = self._prepare_content_for_detection(content_item)
            
            if not content_text:
                logger.warning(f"No content available for pattern detection in item {content_item.get('document_id')}")
                return []
            
            # Detect patterns using pattern detector
            if not self.pattern_detector:
                logger.error("Pattern detector not initialized - skipping pattern detection")
                return []
                
            # Prepare documents list for pattern detector
            documents = [content_item]  # Pattern detector expects a list of documents
            
            # Prepare trial context
            trial_context = {
                'trial_id': trial_id,
                'content_text': content_text
            }
                
            patterns = await self.pattern_detector.detect_patterns(
                trial_id=trial_id,
                documents=documents,
                trial_context=trial_context
            )
            
            if patterns:
                # Add metadata to each pattern
                for pattern in patterns:
                    pattern['trial_id'] = trial_id
                    pattern['document_id'] = content_item.get('document_id')
                    pattern['detection_timestamp'] = self._get_current_timestamp()
                
                return patterns
            
            return []
            
        except Exception as e:
            logger.error(f"Error in pattern detection for item {content_item.get('document_id')}: {e}")
            return []
    
    def _prepare_content_for_detection(self, content_item: Dict[str, Any]) -> str:
        """Prepare content for pattern detection."""
        # Extract text from various fields
        text_parts = []
        
        # Add study card content if available
        if 'summary_text' in content_item:
            text_parts.append(content_item.get('summary_text', ''))
        if 'risks_text' in content_item:
            text_parts.append(content_item.get('risks_text', ''))
        if 'methods_text' in content_item:
            text_parts.append(content_item.get('methods_text', ''))
        if 'population_description' in content_item:
            text_parts.append(content_item.get('population_description', ''))
        if 'primary_endpoint' in content_item:
            text_parts.append(content_item.get('primary_endpoint', ''))
        if 'secondary_endpoints' in content_item:
            endpoints = content_item.get('secondary_endpoints', [])
            if isinstance(endpoints, list):
                text_parts.extend(endpoints)
            else:
                text_parts.append(str(endpoints))
        
        # Add factsheet content from new JSONB sections
        factsheet_sections = content_item.get('factsheet_sections', {})
        if factsheet_sections:
            meaningful_fields = [
                'key_findings', 'efficacy_data', 'safety_data', 
                'mechanism_data', 'biomarker_data', 'dosing_data',
                'population_data', 'limitations'
            ]
            for field in meaningful_fields:
                # Check both lowercase and uppercase field names
                if factsheet_sections.get(field) and str(factsheet_sections[field]).strip():
                    text_parts.append(str(factsheet_sections[field]))
                elif factsheet_sections.get(field.upper()) and str(factsheet_sections[field.upper()]).strip():
                    text_parts.append(str(factsheet_sections[field.upper()]))
        
        # Add normalized facts for better pattern detection
        normalized_facts = content_item.get('normalized_facts', {})
        if normalized_facts:
            # Add mechanism targets
            mechanism_targets = normalized_facts.get('mechanism_targets', [])
            if mechanism_targets:
                text_parts.append(f"Mechanism targets: {', '.join(mechanism_targets)}")
            
            # Add biomarker observations
            biomarkers = normalized_facts.get('biomarkers_observed', [])
            if biomarkers:
                biomarker_text = []
                for biomarker in biomarkers:
                    if isinstance(biomarker, dict):
                        name = biomarker.get('name', '')
                        direction = biomarker.get('direction', '')
                        if name and direction:
                            biomarker_text.append(f"{name}: {direction}")
                if biomarker_text:
                    text_parts.append(f"Biomarkers: {', '.join(biomarker_text)}")
        
        # Legacy factsheet fields for backward compatibility
        if 'results' in content_item:
            results = content_item.get('results', [])
            if isinstance(results, list):
                text_parts.extend([str(r) for r in results])
            else:
                text_parts.append(str(results))
        if 'primary_endpoint_results' in content_item:
            text_parts.append(str(content_item.get('primary_endpoint_results', '')))
        if 'secondary_endpoint_results' in content_item:
            results = content_item.get('secondary_endpoint_results', [])
            if isinstance(results, list):
                text_parts.extend([str(r) for r in results])
            else:
                text_parts.append(str(results))
        if 'safety_results' in content_item:
            results = content_item.get('safety_results', [])
            if isinstance(results, list):
                text_parts.extend([str(r) for r in results])
            else:
                text_parts.append(str(results))
        
        # Add raw text if available
        if 'text' in content_item:
            text_parts.append(content_item['text'])
        
        # Combine all text parts
        combined_text = ' '.join(filter(None, text_parts))
        
        if not combined_text:
            logger.warning(f"No content found for pattern detection in item {content_item.get('document_id')}")
            return ""
        
        # Truncate if too long
        max_length = self.detection_config.get('max_content_length', 10000)
        if len(combined_text) > max_length:
            combined_text = combined_text[:max_length]
            logger.info(f"Truncated content for pattern detection to {max_length} characters")
        
        return combined_text
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp as string."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
