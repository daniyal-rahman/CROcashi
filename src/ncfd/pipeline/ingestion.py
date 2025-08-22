"""
Document ingestion pipeline for trial failure detection.

This module handles the ingestion of trial documents, including parsing,
data extraction, validation, and transformation into structured study cards.
"""

import json
import logging
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Union, Tuple
from pathlib import Path
import hashlib
from dataclasses import dataclass, asdict

from ..db.models import Trial, TrialVersion, Study
from ..db.session import get_session
# Mock function for demo purposes - replace with real extraction in production
def extract_study_card_from_document(document_path):
    """Mock function to extract study card from document."""
    # For demo purposes, return a synthetic study card
    # In production, this would use the actual extraction logic
    return {
        "study_id": f"demo_study_{hash(document_path) % 10000}",
        "is_pivotal": True,
        "primary_type": "efficacy",
        "primary_endpoint_text": "Overall Survival",
        "sample_size": 500,
        "analysis_plan_text": "Standard survival analysis with alpha=0.05",
        "arms": [
            {"name": "Treatment", "sample_size": 250, "dropout_rate": 0.1},
            {"name": "Control", "sample_size": 250, "dropout_rate": 0.1}
        ],
        "alpha": 0.05,
        "interims": 2,
        "assumptions": "Standard survival assumptions",
        "primary_result": {
            "p_value": 0.03,
            "estimate": 0.75,
            "ci_lower": 0.65,
            "ci_upper": 0.85
        }
    }
from ..signals import evaluate_all_signals
from ..scoring import ScoringEngine


@dataclass
class IngestionResult:
    """Result of document ingestion process."""
    success: bool
    trial_id: Optional[str] = None
    version_id: Optional[str] = None
    study_card: Optional[Dict[str, Any]] = None
    extracted_metadata: Optional[Dict[str, Any]] = None
    validation_errors: List[str] = None
    processing_time: float = 0.0
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class DocumentMetadata:
    """Metadata about the ingested document."""
    document_id: str
    source_path: str
    document_type: str
    ingested_at: datetime
    file_size: int
    checksum: str
    source_system: Optional[str] = None
    original_filename: Optional[str] = None
    document_version: Optional[str] = None


class DocumentIngestionPipeline:
    """Comprehensive document ingestion pipeline."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the ingestion pipeline.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        self.scoring_engine = ScoringEngine()
        
        # Default configuration
        self.auto_evaluate_signals = self.config.get("auto_evaluate_signals", True)
        self.auto_score_trials = self.config.get("auto_score_trials", True)
        self.validation_strictness = self.config.get("validation_strictness", "medium")
        self.backup_ingested_data = self.config.get("backup_ingested_data", True)
        
    def ingest_document(self, 
                       document_path: Union[str, Path],
                       trial_metadata: Optional[Dict[str, Any]] = None,
                       run_id: Optional[str] = None) -> IngestionResult:
        """
        Ingest a single document and extract trial data.
        
        Args:
            document_path: Path to the document file
            trial_metadata: Additional trial metadata
            run_id: Run identifier for tracking
            
        Returns:
            IngestionResult with success status and extracted data
        """
        start_time = datetime.now()
        
        try:
            # Validate document path
            if not Path(document_path).exists():
                return IngestionResult(
                    success=False,
                    error_message=f"Document not found: {document_path}"
                )
            
            # Extract document metadata
            doc_metadata = self._extract_document_metadata(document_path)
            
            # Extract study card from document
            study_card = extract_study_card_from_document(document_path)
            if not study_card:
                return IngestionResult(
                    success=False,
                    error_message="Failed to extract study card from document"
                )
            
            # Validate extracted data
            validation_errors = self._validate_study_card(study_card)
            if validation_errors and self.validation_strictness == "strict":
                return IngestionResult(
                    success=False,
                    validation_errors=validation_errors,
                    error_message="Validation failed in strict mode"
                )
            
            # Extract trial metadata
            extracted_metadata = self._extract_trial_metadata(study_card, trial_metadata)
            
            # Store in database
            trial_id, version_id = self._store_trial_data(
                study_card, extracted_metadata, doc_metadata, run_id
            )
            
            # Auto-evaluate signals if enabled
            if self.auto_evaluate_signals:
                self._evaluate_signals_for_trial(trial_id, study_card)
            
            # Auto-score trial if enabled
            if self.auto_score_trials:
                self._score_trial(trial_id, extracted_metadata, run_id)
            
            # Backup data if enabled
            if self.backup_ingested_data:
                self._backup_ingested_data(study_card, extracted_metadata, doc_metadata)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            self.logger.info(f"Successfully ingested document: {document_path} -> Trial {trial_id}")
            
            return IngestionResult(
                success=True,
                trial_id=trial_id,
                version_id=version_id,
                study_card=study_card,
                extracted_metadata=extracted_metadata,
                validation_errors=validation_errors,
                processing_time=processing_time,
                metadata={
                    "document_metadata": asdict(doc_metadata),
                    "run_id": run_id
                }
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            self.logger.error(f"Document ingestion failed: {document_path}, Error: {e}")
            
            return IngestionResult(
                success=False,
                error_message=str(e),
                processing_time=processing_time
            )
    
    def batch_ingest_documents(self, 
                              document_paths: List[Union[str, Path]],
                              trial_metadata_list: Optional[List[Dict[str, Any]]] = None,
                              run_id: Optional[str] = None) -> List[IngestionResult]:
        """
        Ingest multiple documents in batch.
        
        Args:
            document_paths: List of document paths
            trial_metadata_list: List of trial metadata (optional)
            run_id: Run identifier for tracking
            
        Returns:
            List of IngestionResult objects
        """
        results = []
        
        self.logger.info(f"Starting batch ingestion of {len(document_paths)} documents")
        
        for i, doc_path in enumerate(document_paths):
            trial_metadata = trial_metadata_list[i] if trial_metadata_list else None
            
            self.logger.info(f"Processing document {i+1}/{len(document_paths)}: {doc_path}")
            
            result = self.ingest_document(doc_path, trial_metadata, run_id)
            results.append(result)
            
            # Log progress
            if result.success:
                self.logger.info(f"✅ Document {i+1} ingested successfully")
            else:
                self.logger.warning(f"❌ Document {i+1} failed: {result.error_message}")
        
        # Summary statistics
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        
        self.logger.info(f"Batch ingestion completed: {successful} successful, {failed} failed")
        
        return results
    
    def validate_ingested_data(self, study_card: Dict[str, Any]) -> List[str]:
        """
        Validate ingested study card data.
        
        Args:
            study_card: Extracted study card data
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Required fields validation
        required_fields = ["study_id", "is_pivotal", "primary_type"]
        for field in required_fields:
            if field not in study_card or study_card[field] is None:
                errors.append(f"Missing required field: {field}")
        
        # Arms validation
        if "arms" in study_card:
            arms = study_card["arms"]
            if not isinstance(arms, dict):
                errors.append("Arms must be a dictionary")
            else:
                if "t" not in arms:
                    errors.append("Treatment arm (t) is required")
                elif not isinstance(arms["t"], dict):
                    errors.append("Treatment arm must be a dictionary")
                elif "n" not in arms["t"]:
                    errors.append("Treatment arm sample size (n) is required")
        
        # Analysis plan validation
        if "analysis_plan" in study_card:
            plan = study_card["analysis_plan"]
            if not isinstance(plan, dict):
                errors.append("Analysis plan must be a dictionary")
            else:
                if "alpha" in plan:
                    alpha = plan["alpha"]
                    if not isinstance(alpha, (int, float)) or alpha <= 0 or alpha >= 1:
                        errors.append("Alpha must be between 0 and 1")
        
        # Primary result validation
        if "primary_result" in study_card:
            result = study_card["primary_result"]
            if not isinstance(result, dict):
                errors.append("Primary result must be a dictionary")
            elif "ITT" in result:
                itt = result["ITT"]
                if not isinstance(itt, dict):
                    errors.append("ITT result must be a dictionary")
                elif "p" in itt:
                    p_val = itt["p"]
                    if not isinstance(p_val, (int, float)) or p_val < 0 or p_val > 1:
                        errors.append("P-value must be between 0 and 1")
        
        return errors
    
    def _extract_document_metadata(self, document_path: Union[str, Path]) -> DocumentMetadata:
        """Extract metadata from the document."""
        path = Path(document_path)
        
        # Calculate file checksum
        with open(path, 'rb') as f:
            content = f.read()
            checksum = hashlib.md5(content).hexdigest()
        
        # Determine document type
        if path.suffix.lower() in ['.pdf', '.PDF']:
            doc_type = "pdf"
        elif path.suffix.lower() in ['.txt', '.TXT']:
            doc_type = "text"
        elif path.suffix.lower() in ['.html', '.HTML', '.htm', '.HTM']:
            doc_type = "html"
        else:
            doc_type = "unknown"
        
        return DocumentMetadata(
            document_id=checksum,
            source_path=str(path),
            document_type=doc_type,
            ingested_at=datetime.now(),
            file_size=len(content),
            checksum=checksum,
            original_filename=path.name
        )
    
    def _extract_trial_metadata(self, 
                               study_card: Dict[str, Any],
                               additional_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract trial metadata from study card and additional sources."""
        metadata = {
            "trial_id": study_card.get("study_id"),
            "is_pivotal": study_card.get("is_pivotal", False),
            "indication": study_card.get("indication", "unknown"),
            "phase": study_card.get("phase", "unknown"),
            "sponsor": study_card.get("sponsor", "unknown"),
            "drug_name": study_card.get("drug_name", "unknown"),
            "primary_endpoint_type": study_card.get("primary_type", "unknown"),
            "extracted_at": datetime.now().isoformat(),
            "source": "document_ingestion"
        }
        
        # Add additional metadata if provided
        if additional_metadata:
            metadata.update(additional_metadata)
        
        # Infer sponsor experience if not provided
        if "sponsor_experience" not in metadata:
            # Simple heuristic based on sponsor name
            sponsor = metadata.get("sponsor", "").lower()
            if any(exp in sponsor for exp in ["merck", "pfizer", "novartis", "roche", "astrazeneca"]):
                metadata["sponsor_experience"] = "experienced"
            else:
                metadata["sponsor_experience"] = "unknown"
        
        return metadata
    
    def _validate_study_card(self, study_card: Dict[str, Any]) -> List[str]:
        """Validate study card data."""
        return self.validate_ingested_data(study_card)
    
    def _store_trial_data(self, 
                          study_card: Dict[str, Any],
                          metadata: Dict[str, Any],
                          doc_metadata: DocumentMetadata,
                          run_id: Optional[str] = None) -> Tuple[str, str]:
        """Store trial data in the database."""
        with get_session() as session:
            # Create or update trial
            trial = session.query(Trial).filter_by(trial_id=metadata["trial_id"]).first()
            
            if not trial:
                trial = Trial(
                    trial_id=metadata["trial_id"],
                    is_pivotal=metadata["is_pivotal"],
                    indication=metadata["indication"],
                    phase=metadata["phase"],
                    sponsor=metadata["sponsor"],
                    drug_name=metadata["drug_name"],
                    primary_endpoint_type=metadata["primary_endpoint_type"],
                    sponsor_experience=metadata.get("sponsor_experience", "unknown"),
                    created_at=datetime.now(),
                    metadata=metadata
                )
                session.add(trial)
            else:
                # Update existing trial
                trial.is_pivotal = metadata["is_pivotal"]
                trial.indication = metadata["indication"]
                trial.phase = metadata["phase"]
                trial.sponsor = metadata["sponsor"]
                trial.drug_name = metadata["drug_name"]
                trial.primary_endpoint_type = metadata["primary_endpoint_type"]
                trial.sponsor_experience = metadata.get("sponsor_experience", "unknown")
                trial.updated_at = datetime.now()
                trial.metadata.update(metadata)
            
            # Create trial version
            trial_version = TrialVersion(
                trial_id=trial.trial_id,
                captured_at=datetime.now(),
                raw_jsonb=study_card,
                primary_endpoint_text=study_card.get("primary_endpoint_text", ""),
                sample_size=metadata.get("sample_size"),
                analysis_plan_text=study_card.get("analysis_plan_text", ""),
                changes_jsonb={},
                metadata={
                    "document_metadata": asdict(doc_metadata),
                    "run_id": run_id,
                    "ingestion_method": "document_pipeline"
                }
            )
            session.add(trial_version)
            
            session.commit()
            
            return trial.trial_id, trial_version.version_id
    
    def _evaluate_signals_for_trial(self, trial_id: str, study_card: Dict[str, Any]) -> None:
        """Evaluate signals for the ingested trial."""
        try:
            signals = evaluate_all_signals(study_card)
            
            # Store signals in database (this would be implemented in the signals module)
            self.logger.info(f"Evaluated {len(signals)} signals for trial {trial_id}")
            
        except Exception as e:
            self.logger.error(f"Signal evaluation failed for trial {trial_id}: {e}")
    
    def _score_trial(self, trial_id: str, metadata: Dict[str, Any], run_id: Optional[str] = None) -> None:
        """Score the ingested trial."""
        try:
            # Get gates for the trial (this would be implemented in the gates module)
            # For now, create empty gates
            gates = {}
            
            score = self.scoring_engine.score_trial(trial_id, metadata, gates, run_id or "ingestion")
            
            self.logger.info(f"Scored trial {trial_id}: {score.p_fail:.3f} failure probability")
            
        except Exception as e:
            self.logger.error(f"Trial scoring failed for trial {trial_id}: {e}")
    
    def _backup_ingested_data(self, 
                             study_card: Dict[str, Any],
                             metadata: Dict[str, Any],
                             doc_metadata: DocumentMetadata) -> None:
        """Backup ingested data for audit purposes."""
        backup_data = {
            "study_card": study_card,
            "metadata": metadata,
            "document_metadata": asdict(doc_metadata),
            "backup_timestamp": datetime.now().isoformat()
        }
        
        # Create backup directory if it doesn't exist
        backup_dir = Path("data/backups/ingestion")
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Save backup file
        backup_file = backup_dir / f"backup_{doc_metadata.checksum}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2, default=str)
        
        self.logger.info(f"Backed up ingested data to {backup_file}")


# Convenience functions
def ingest_document(document_path: Union[str, Path],
                   trial_metadata: Optional[Dict[str, Any]] = None,
                   run_id: Optional[str] = None) -> IngestionResult:
    """Ingest a single document."""
    pipeline = DocumentIngestionPipeline()
    return pipeline.ingest_document(document_path, trial_metadata, run_id)


def batch_ingest_documents(document_paths: List[Union[str, Path]],
                          trial_metadata_list: Optional[List[Dict[str, Any]]] = None,
                          run_id: Optional[str] = None) -> List[IngestionResult]:
    """Ingest multiple documents in batch."""
    pipeline = DocumentIngestionPipeline()
    return pipeline.batch_ingest_documents(document_paths, trial_metadata_list, run_id)


def validate_ingested_data(study_card: Dict[str, Any]) -> List[str]:
    """Validate ingested study card data."""
    pipeline = DocumentIngestionPipeline()
    return pipeline.validate_ingested_data(study_card)
