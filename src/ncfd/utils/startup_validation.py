"""
Startup Validation Utilities

Comprehensive validation checks to run at application startup to prevent
degenerate study cards and other runtime failures.
"""

import logging
import os
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

logger = logging.getLogger(__name__)


class StartupValidator:
    """Comprehensive startup validation for the NCFD system."""
    
    def __init__(self):
        self.validation_results = {
            'pubmed_config': {'passed': False, 'errors': []},
            'basespan_config': {'passed': False, 'errors': []},
            'database_connectivity': {'passed': False, 'errors': []},
            'sec_universe': {'passed': False, 'errors': []},
            'environment_variables': {'passed': False, 'errors': []},
            'file_permissions': {'passed': False, 'errors': []}
        }
    
    def run_all_validations(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Run all startup validations.
        
        Returns:
            Tuple of (all_passed, validation_results)
        """
        logger.info("🔍 Running startup validations...")
        
        # Run individual validations
        self._validate_pubmed_config()
        self._validate_basespan_config()
        self._validate_database_connectivity()
        self._validate_sec_universe()
        self._validate_environment_variables()
        self._validate_file_permissions()
        
        # Determine overall success
        all_passed = all(result['passed'] for result in self.validation_results.values())
        
        # Log summary
        self._log_validation_summary(all_passed)
        
        return all_passed, self.validation_results
    
    def _validate_pubmed_config(self):
        """Validate PubMed pipeline configuration."""
        logger.info("Validating PubMed configuration...")
        errors = []
        
        try:
            # Check for required configuration values
            from ..pipeline.pubmed_pipeline import PubMedPipeline
            
            # Test config with minimal requirements
            test_config = {
                'enable_pmcid_linking': True,
                'enable_oa_detection': True,
                'rate_limit_per_sec': 1,
                'asset_names': ['test'],
                'indications': ['test']
            }
            
            # Try to instantiate pipeline
            try:
                pipeline = PubMedPipeline(test_config)
                
                # Check rate limiting configuration
                if hasattr(pipeline, 'client') and hasattr(pipeline.client, 'rate_limit_per_sec'):
                    if pipeline.client.rate_limit_per_sec <= 0:
                        errors.append("PubMed rate_limit_per_sec must be > 0 to avoid division by zero")
                
                # Check async methods exist
                if not hasattr(pipeline, 'run_daily_ingestion'):
                    errors.append("PubMed pipeline missing run_daily_ingestion method")
                
                if not hasattr(pipeline, 'run_oa_for_trial'):
                    errors.append("PubMed pipeline missing run_oa_for_trial method")
                
            except Exception as e:
                errors.append(f"Failed to instantiate PubMed pipeline: {e}")
            
        except ImportError as e:
            errors.append(f"Failed to import PubMed pipeline: {e}")
        except Exception as e:
            errors.append(f"PubMed config validation error: {e}")
        
        self.validation_results['pubmed_config'] = {
            'passed': len(errors) == 0,
            'errors': errors
        }
    
    def _validate_basespan_config(self):
        """Validate BaseSpan configuration."""
        logger.info("Validating BaseSpan configuration...")
        errors = []
        
        try:
            # Check if config file exists
            config_path = Path("src/ncfd/extract/config/span_config.yaml")
            if not config_path.exists():
                errors.append(f"BaseSpan config file not found: {config_path}")
                self.validation_results['basespan_config'] = {
                    'passed': False,
                    'errors': errors
                }
                return
            
            # Load and validate config
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Check required sections
            required_sections = ['span_generation', 'span_indexing', 'span_triage']
            for section in required_sections:
                if section not in config:
                    errors.append(f"BaseSpan config missing required section: {section}")
            
            # Validate span_generation
            if 'span_generation' in config:
                gen_config = config['span_generation']
                required_gen_fields = ['min_sentence_length', 'max_sentence_length']
                for field in required_gen_fields:
                    if field not in gen_config:
                        errors.append(f"BaseSpan span_generation missing field: {field}")
                
                # Validate ranges
                if ('min_sentence_length' in gen_config and 
                    'max_sentence_length' in gen_config):
                    if gen_config['min_sentence_length'] >= gen_config['max_sentence_length']:
                        errors.append("BaseSpan min_sentence_length must be < max_sentence_length")
            
            # Validate span_indexing
            if 'span_indexing' in config:
                indexing_config = config['span_indexing']
                if 'bm25' not in indexing_config:
                    errors.append("BaseSpan span_indexing missing bm25 configuration")
                else:
                    bm25_config = indexing_config['bm25']
                    if not isinstance(bm25_config.get('enabled'), bool):
                        errors.append("BaseSpan bm25.enabled must be boolean")
            
            # Validate span_triage
            if 'span_triage' in config:
                triage_config = config['span_triage']
                if 'budgets' not in triage_config:
                    errors.append("BaseSpan span_triage missing budgets configuration")
        
        except yaml.YAMLError as e:
            errors.append(f"BaseSpan config YAML error: {e}")
        except Exception as e:
            errors.append(f"BaseSpan config validation error: {e}")
        
        self.validation_results['basespan_config'] = {
            'passed': len(errors) == 0,
            'errors': errors
        }
    
    def _validate_database_connectivity(self):
        """Validate database connectivity and table existence."""
        logger.info("Validating database connectivity...")
        errors = []
        
        try:
            from ..db.session import get_session
            from ..db.models import Trial, Document, DocumentText, DocumentLink
            
            with get_session() as session:
                # Try basic queries on key tables
                try:
                    session.query(Trial).count()
                except Exception as e:
                    errors.append(f"Cannot query trials table: {e}")
                
                try:
                    session.query(Document).count()
                except Exception as e:
                    errors.append(f"Cannot query documents table: {e}")
                
                try:
                    session.query(DocumentText).count()
                except Exception as e:
                    errors.append(f"Cannot query document_text table: {e}")
                
                try:
                    session.query(DocumentLink).count()
                except Exception as e:
                    errors.append(f"Cannot query document_link table: {e}")
        
        except Exception as e:
            errors.append(f"Database connectivity error: {e}")
        
        self.validation_results['database_connectivity'] = {
            'passed': len(errors) == 0,
            'errors': errors
        }
    
    def _validate_sec_universe(self):
        """Validate SEC universe configuration."""
        logger.info("Validating SEC universe...")
        errors = []
        
        try:
            from ..pipeline.orchestrator import PipelineOrchestrator
            
            # Test orchestrator instantiation
            test_config = {'monitored_companies': []}
            try:
                orchestrator = PipelineOrchestrator(test_config)
                
                # Check if universe is populated
                if hasattr(orchestrator, 'sec_pipeline') and hasattr(orchestrator.sec_pipeline, 'monitored_companies'):
                    if len(orchestrator.sec_pipeline.monitored_companies) == 0:
                        errors.append("SEC universe is empty - no monitored companies configured")
                else:
                    errors.append("SEC pipeline missing monitored_companies attribute")
            
            except Exception as e:
                errors.append(f"Failed to instantiate SEC pipeline: {e}")
        
        except ImportError as e:
            errors.append(f"Failed to import SEC pipeline: {e}")
        except Exception as e:
            errors.append(f"SEC universe validation error: {e}")
        
        self.validation_results['sec_universe'] = {
            'passed': len(errors) == 0,
            'errors': errors
        }
    
    def _validate_environment_variables(self):
        """Validate required environment variables."""
        logger.info("Validating environment variables...")
        errors = []
        
        # Check required environment variables
        required_env_vars = [
            'DATABASE_URL',
            'OPENAI_API_KEY'
        ]
        
        for var in required_env_vars:
            value = os.getenv(var)
            if not value:
                errors.append(f"Required environment variable not set: {var}")
            elif var == 'DATABASE_URL' and 'test' not in value.lower():
                # Warn about production database usage
                logger.warning(f"Using non-test database: {value}")
        
        # Validate DATABASE_URL format
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            if not (database_url.startswith('postgresql://') or 
                   database_url.startswith('sqlite://')):
                errors.append(f"Unsupported DATABASE_URL format: {database_url}")
        
        self.validation_results['environment_variables'] = {
            'passed': len(errors) == 0,
            'errors': errors
        }
    
    def _validate_file_permissions(self):
        """Validate file and directory permissions."""
        logger.info("Validating file permissions...")
        errors = []
        
        # Check key directories and files
        paths_to_check = [
            'src/ncfd/extract/config/',
            'src/ncfd/extract/config/span_config.yaml',
            '.state/',  # For orchestrator state
            'data/'     # For data storage (if exists)
        ]
        
        for path_str in paths_to_check:
            path = Path(path_str)
            
            if path.exists():
                try:
                    if path.is_dir():
                        # Check if directory is writable
                        test_file = path / '.write_test'
                        try:
                            test_file.touch()
                            test_file.unlink()
                        except Exception as e:
                            errors.append(f"Directory not writable: {path} ({e})")
                    else:
                        # Check if file is readable
                        try:
                            path.read_text()
                        except Exception as e:
                            errors.append(f"File not readable: {path} ({e})")
                
                except Exception as e:
                    errors.append(f"Permission check failed for {path}: {e}")
            else:
                # Try to create directory if it doesn't exist
                if path_str.endswith('/'):
                    try:
                        path.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        errors.append(f"Cannot create directory: {path} ({e})")
        
        self.validation_results['file_permissions'] = {
            'passed': len(errors) == 0,
            'errors': errors
        }
    
    def _log_validation_summary(self, all_passed: bool):
        """Log validation summary."""
        if all_passed:
            logger.info("✅ All startup validations passed")
        else:
            logger.error("❌ Some startup validations failed")
            
            for validation_name, result in self.validation_results.items():
                if not result['passed']:
                    logger.error(f"❌ {validation_name}: {len(result['errors'])} errors")
                    for error in result['errors']:
                        logger.error(f"   • {error}")
                else:
                    logger.info(f"✅ {validation_name}: passed")


def run_startup_validation(fail_fast: bool = True) -> bool:
    """
    Run startup validation and optionally exit on failure.
    
    Args:
        fail_fast: Whether to raise exception on validation failure
        
    Returns:
        True if all validations passed
        
    Raises:
        RuntimeError: If fail_fast=True and validations fail
    """
    validator = StartupValidator()
    all_passed, results = validator.run_all_validations()
    
    if not all_passed and fail_fast:
        error_summary = []
        for validation_name, result in results.items():
            if not result['passed']:
                error_summary.extend([f"{validation_name}: {error}" for error in result['errors']])
        
        raise RuntimeError(f"Startup validation failed:\n" + "\n".join(error_summary))
    
    return all_passed


def validate_config_before_pipeline_run(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate configuration before running pipelines.
    
    Args:
        config: Pipeline configuration
        
    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []
    
    # Validate PubMed config
    pubmed_config = config.get('pubmed', {})
    if 'rate_limit_per_sec' in pubmed_config:
        if pubmed_config['rate_limit_per_sec'] <= 0:
            errors.append("PubMed rate_limit_per_sec must be > 0")
    
    # Validate quality gate config
    quality_config = config.get('quality_gate', {})
    if quality_config:
        min_confidence = quality_config.get('min_confidence', 0.55)
        if min_confidence < 0 or min_confidence > 1:
            errors.append("Quality gate min_confidence must be between 0 and 1")
    
    return len(errors) == 0, errors
