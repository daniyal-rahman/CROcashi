"""
Span Configuration Loader

Loads and validates configuration for the BaseSpan system.
"""

import os
import yaml
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SpanGenerationConfig:
    """Configuration for span generation."""
    min_sentence_length: int = 12
    max_sentence_length: int = 400
    min_table_cell_length: int = 1  # Reduced from 10 to capture short numeric values
    max_table_cell_length: int = 500  # Increased from 200 to allow longer cells
    preserve_hyphens: bool = False
    normalize_whitespace: bool = True
    include_paragraph_spans: bool = False


@dataclass
class BM25Config:
    """Configuration for BM25 indexing."""
    k1: float = 1.2
    b: float = 0.75
    max_features: int = 10000
    normalize_tokens: bool = True
    preserve_numerics: bool = True


@dataclass
class DenseConfig:
    """Configuration for dense indexing."""
    dimension: int = 768
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    fallback_to_tfidf: bool = True


@dataclass
class IndexingConfig:
    """Configuration for indexing."""
    bm25: BM25Config = None
    dense: DenseConfig = None
    
    def __post_init__(self):
        if self.bm25 is None:
            self.bm25 = BM25Config()
        if self.dense is None:
            self.dense = DenseConfig()


@dataclass
class FuzzyAlignmentConfig:
    """Configuration for fuzzy alignment."""
    similarity_threshold: float = 0.85
    use_levenshtein: bool = True
    use_sequence_matcher: bool = True
    use_token_set: bool = True
    normalize_text: bool = True
    preserve_case: bool = False
    max_derived_span_length: int = 1000


@dataclass
class TriageBudgets:
    """Budget configuration for span triage."""
    methods: int = 12
    results: int = 12
    tables: int = 5


@dataclass
class TopupConfig:
    """Configuration for top-up attempts."""
    per_field: int = 3
    max_attempts: int = 1


@dataclass
class RetrievalConfig:
    """Configuration for retrieval."""
    use_bm25: bool = True
    use_dense: bool = True
    min_similarity_threshold: float = 0.3


@dataclass
class MustHitSlots:
    """Configuration for must-hit slots."""
    statistics_km: int = 2
    endpoints_recist: int = 2
    design_archetype: int = 2
    response_breakdown: int = 2
    survival_medians: int = 2


@dataclass
class SpanTriageConfig:
    """Configuration for span triage."""
    budgets: TriageBudgets = None
    topup: TopupConfig = None
    retrieval: RetrievalConfig = None
    must_hit_slots: MustHitSlots = None
    
    def __post_init__(self):
        if self.budgets is None:
            self.budgets = TriageBudgets()
        if self.topup is None:
            self.topup = TopupConfig()
        if self.retrieval is None:
            self.retrieval = RetrievalConfig()
        if self.must_hit_slots is None:
            self.must_hit_slots = MustHitSlots()


@dataclass
class SystemFlags:
    """System-wide configuration flags."""
    retriever_mode: str = "bm25_dense_union"
    llm_assist_mode: str = "on"
    factsbin_mode: str = "both"
    km_inference_policy: str = "strict"
    provenance_enforcement: str = "hard"


@dataclass
class TableProcessingConfig:
    """Configuration for table processing."""
    min_cell_length: int = 10
    max_cell_length: int = 200
    include_headers: bool = True
    include_captions: bool = True
    preserve_structure: bool = True


@dataclass
class PerformanceConfig:
    """Configuration for performance settings."""
    batch_size: int = 100
    max_workers: int = 4
    timeout_seconds: int = 300
    memory_limit_mb: int = 2048


@dataclass
class SpanConfig:
    """Complete configuration for the BaseSpan system."""
    span_generation: SpanGenerationConfig = None
    indexing: IndexingConfig = None
    fuzzy_alignment: FuzzyAlignmentConfig = None
    span_triage: SpanTriageConfig = None
    system_flags: SystemFlags = None
    default_required_fields: list = None
    section_patterns: Dict[str, list] = None
    table_processing: TableProcessingConfig = None
    performance: PerformanceConfig = None
    
    def __post_init__(self):
        if self.span_generation is None:
            self.span_generation = SpanGenerationConfig()
        if self.indexing is None:
            self.indexing = IndexingConfig()
        if self.fuzzy_alignment is None:
            self.fuzzy_alignment = FuzzyAlignmentConfig()
        if self.span_triage is None:
            self.span_triage = SpanTriageConfig()
        if self.system_flags is None:
            self.system_flags = SystemFlags()
        if self.default_required_fields is None:
            self.default_required_fields = [
                "endpoints", "ascertainment", "survival_method", "design_archetype",
                "interim_looks", "analysis_denominators", "site_geography",
                "response_breakdown", "survival_medians", "tables"
            ]
        if self.section_patterns is None:
            self.section_patterns = {
                "methods": ["methods", "materials and methods", "study design", "protocol",
                           "statistical analysis", "sample size", "randomization"],
                "results": ["results", "outcomes", "efficacy", "response rate", "survival",
                           "median", "progression-free", "overall survival"],
                "abstract": ["abstract", "background", "objective", "conclusion"],
                "discussion": ["discussion", "interpretation", "clinical implications"]
            }
        if self.table_processing is None:
            self.table_processing = TableProcessingConfig()
        if self.performance is None:
            self.performance = PerformanceConfig()


class SpanConfigLoader:
    """Loader for span configuration files."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the config loader."""
        if config_path is None:
            # Default to main config directory
            project_root = Path(__file__).parent.parent.parent.parent
            config_path = project_root / "config" / "basespan_config.yaml"
        
        self.config_path = Path(config_path)
        self._config = None
    
    def load_config(self) -> SpanConfig:
        """Load configuration from file."""
        if self._config is not None:
            return self._config
        
        if not self.config_path.exists():
            # Return default configuration if file doesn't exist
            self._config = SpanConfig()
            return self._config
        
        try:
            with open(self.config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            # Parse configuration into dataclasses
            self._config = self._parse_config(config_data)
            return self._config
            
        except Exception as e:
            print(f"Warning: Failed to load span config from {self.config_path}: {e}")
            print("Using default configuration")
            self._config = SpanConfig()
            return self._config
    
    def _parse_config(self, config_data: Dict[str, Any]) -> SpanConfig:
        """Parse configuration data into dataclass instances."""
        # Parse span generation config
        span_gen_data = config_data.get('span_generation', {})
        span_generation = SpanGenerationConfig(**span_gen_data)
        
        # Parse indexing config
        indexing_data = config_data.get('indexing', {})
        bm25_data = indexing_data.get('bm25', {})
        dense_data = indexing_data.get('dense', {})
        
        bm25 = BM25Config(**bm25_data)
        dense = DenseConfig(**dense_data)
        indexing = IndexingConfig(bm25=bm25, dense=dense)
        
        # Parse fuzzy alignment config
        fuzzy_data = config_data.get('fuzzy_alignment', {})
        fuzzy_alignment = FuzzyAlignmentConfig(**fuzzy_data)
        
        # Parse span triage config
        triage_data = config_data.get('span_triage', {})
        budgets_data = triage_data.get('budgets', {})
        topup_data = triage_data.get('topup', {})
        retrieval_data = triage_data.get('retrieval', {})
        must_hit_data = triage_data.get('must_hit_slots', {})
        
        budgets = TriageBudgets(**budgets_data)
        topup = TopupConfig(**topup_data)
        retrieval = RetrievalConfig(**retrieval_data)
        must_hit_slots = MustHitSlots(**must_hit_data)
        span_triage = SpanTriageConfig(
            budgets=budgets, topup=topup, retrieval=retrieval, must_hit_slots=must_hit_slots
        )
        
        # Parse system flags
        flags_data = config_data.get('system_flags', {})
        system_flags = SystemFlags(**flags_data)
        
        # Parse other configs
        default_required_fields = config_data.get('default_required_fields', [])
        section_patterns = config_data.get('section_patterns', {})
        
        table_data = config_data.get('table_processing', {})
        table_processing = TableProcessingConfig(**table_data)
        
        perf_data = config_data.get('performance', {})
        performance = PerformanceConfig(**perf_data)
        
        return SpanConfig(
            span_generation=span_generation,
            indexing=indexing,
            fuzzy_alignment=fuzzy_alignment,
            span_triage=span_triage,
            system_flags=system_flags,
            default_required_fields=default_required_fields,
            section_patterns=section_patterns,
            table_processing=table_processing,
            performance=performance
        )
    
    def reload_config(self) -> SpanConfig:
        """Reload configuration from file."""
        self._config = None
        return self.load_config()
    
    def get_config(self) -> SpanConfig:
        """Get the current configuration (load if necessary)."""
        return self.load_config()
    
    def validate_config(self) -> bool:
        """Validate the current configuration."""
        try:
            config = self.get_config()
            
            # Validate numeric ranges
            if config.span_generation.min_sentence_length <= 0:
                return False
            if config.span_generation.max_sentence_length <= config.span_generation.min_sentence_length:
                return False
            if config.fuzzy_alignment.similarity_threshold < 0 or config.fuzzy_alignment.similarity_threshold > 1:
                return False
            
            # Validate system flags
            valid_retriever_modes = ["bm25_only", "dense_only", "bm25_dense_union"]
            if config.system_flags.retriever_mode not in valid_retriever_modes:
                return False
            
            valid_llm_modes = ["on", "off"]
            if config.system_flags.llm_assist_mode not in valid_llm_modes:
                return False
            
            return True
            
        except Exception:
            return False


# Global configuration instance
_global_config = None


def get_span_config() -> SpanConfig:
    """Get the global span configuration instance."""
    global _global_config
    if _global_config is None:
        loader = SpanConfigLoader()
        _global_config = loader.load_config()
    return _global_config


def reload_span_config() -> SpanConfig:
    """Reload the global span configuration."""
    global _global_config
    loader = SpanConfigLoader()
    _global_config = loader.reload_config()
    return _global_config
