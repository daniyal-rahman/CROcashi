"""
Retriever Worker

Document retrieval and triage worker for finding high-quality evidence spans.
Uses production-grade BM25 indexing via Pyserini for optimal retrieval quality.
"""

from typing import Any, Dict, List, Optional
from .base_worker import BaseWorker, WorkerResult
from .span_triage import SpanTriageWorker, TriageConfig, TriageQuery
from .bm25_indexer import BM25Indexer, BM25Config
from ..models import DocumentCard, EvidenceSpan
from ...db.models import BaseSpan, Document
from ...db.session import get_session
from ...utils.study_card_utils import generate_span_id, validate_span_coordinates


class Retriever(BaseWorker):
    """Worker for document retrieval and evidence span triage."""
    
    def __init__(self, max_span_length: int = 400, min_confidence: float = 0.7):
        super().__init__("Retriever", "2.0.0")
        self.max_span_length = max_span_length
        self.min_confidence = min_confidence
        self.span_triage = SpanTriageWorker()
        
        # Initialize BM25 indexer with production-grade configuration
        bm25_config = BM25Config(
            k1=1.2,
            b=0.75,
            index_path="data/bm25_index",
            analyzer_name="EnglishAnalyzer",
            use_field_boosts=True
        )
        self.bm25_indexer = BM25Indexer(bm25_config)
        
        # Must-hit token patterns for critical fields - will be populated from config
        self.must_hit_tokens = self._load_must_hit_tokens()
        
    def _load_must_hit_tokens(self) -> Dict[str, List[str]]:
        """Load must-hit tokens from query synonym configuration."""
        from ..query_synonym_manager import query_synonym_manager
        
        # Get all must-hit synonyms from config
        must_hit_synonyms = query_synonym_manager.get_all_must_hit_synonyms()
        
        # Map to the expected field structure
        must_hit_tokens = {
            "statistics_km": must_hit_synonyms.get("km", ["kaplan-meier", "km", "survival analysis", "log-rank"]),
            "endpoints_recist": must_hit_synonyms.get("recist", ["recist", "response rate", "objective response", "complete response"]),
            "design_archetype": must_hit_synonyms.get("gehan", ["gehan", "two-stage", "interim analysis", "stopping rules"]),
            "response_breakdown": ["orr", "cr", "pr", "sd", "pd", "objective response rate"],  # Keep existing for response breakdown
            "survival_medians": must_hit_synonyms.get("ttp", []) + must_hit_synonyms.get("os", []) + ["median", "pfs", "progression-free"]
        }
        
        return must_hit_tokens
    
    def _validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate inputs for Retriever."""
        required_keys = ["trial_context"]
        
        if not all(key in inputs for key in required_keys):
            return False
            
        if not isinstance(inputs["trial_context"], dict):
            return False
            
        return True
    
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Process inputs to retrieve documents and create evidence spans."""
        try:
            trial_context = inputs["trial_context"]
            date_window = inputs.get("date_window", "2020-2024")
            rebuild_bm25_index = inputs.get("rebuild_bm25_index", False)
            
            # Build/rebuild BM25 index if needed
            if rebuild_bm25_index:
                bm25_result = self.bm25_indexer.process({"rebuild_all": True})
                if not bm25_result.success:
                    return WorkerResult(
                        success=False,
                        output=None,
                        error_message=f"Failed to build BM25 index: {bm25_result.error_message}"
                    )
            
            # Retrieve documents based on trial context
            use_real_retrieval = inputs.get("use_real_retrieval", False)
            document_cards = self._retrieve_documents(trial_context, date_window, use_real_retrieval)
            
            # Extract BaseSpans from documents and perform triage
            evidence_spans = self._extract_and_triage_spans(document_cards, trial_context)
            
            # Add provenance
            for i, doc_card in enumerate(document_cards):
                document_cards[i] = self._add_provenance(doc_card, inputs)
            
            for i, span in enumerate(evidence_spans):
                evidence_spans[i] = self._add_provenance(span, inputs)
            
            return WorkerResult(
                success=True,
                output={
                    "document_cards": document_cards,
                    "evidence_spans": evidence_spans
                },
                metadata={
                    "documents_retrieved": len(document_cards),
                    "spans_extracted": len(evidence_spans),
                    "date_window": date_window,
                    "budgets_enforced": True,
                    "must_hit_tokens_reserved": True,
                    "bm25_index_used": True,
                    "bm25_index_stats": self.bm25_indexer.get_index_stats(),
                    "mock_documents": not use_real_retrieval,  # Indicate whether documents are mock
                    "real_retrieval_requested": use_real_retrieval
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Retriever failed: {str(e)}"
            )
    
    def _retrieve_documents(self, trial_context: Dict[str, Any], 
                           date_window: str, use_real_retrieval: bool = False) -> List[DocumentCard]:
        """Retrieve relevant documents based on trial context."""
        documents = []
        
        # Extract key information from trial context
        disease = trial_context.get("disease", "")
        intervention = trial_context.get("intervention", "")
        study_type = trial_context.get("study_type", "")
        
        if use_real_retrieval:
            # TODO: Implement real document retrieval from database/APIs
            # This would query the Document table and other sources
            # For now, fall back to mock documents
            print("Warning: Real document retrieval not yet implemented, using mock documents")
        
        # Create mock documents for testing/development
        if disease and intervention:
            # Create a mock document card for testing
            doc_card = DocumentCard(
                doc_id=f"ctgov:{trial_context.get('trial_id', 'NCT12345')}",
                doc_type="Paper",
                title=f"Study of {intervention} in {disease}",
                year=2023
            )
            
            # Add metadata
            doc_card.disease = disease
            doc_card.intervention = intervention
            doc_card.study_type = study_type or "RCT"
            doc_card.venue = "Clinical Trial"
            
            # Add fulltext references
            doc_card.add_fulltext_ref(1, 0, 500, "text")
            doc_card.add_fulltext_ref(2, 0, 600, "text")
            doc_card.add_fulltext_ref(3, 0, 400, "text")
            
            documents.append(doc_card)
        
        return documents
    
    def _extract_and_triage_spans(self, document_cards: List[DocumentCard], 
                                 trial_context: Dict[str, Any]) -> List[EvidenceSpan]:
        """Extract BaseSpans from documents and perform budgeted triage."""
        all_evidence_spans = []
        
        for doc_card in document_cards:
            # Get BaseSpans from database
            base_spans = self._get_base_spans_from_document(doc_card.doc_id)
            
            if not base_spans:
                continue
            
            # Perform span triage with budgets and must-hit tokens
            triaged_spans = self._perform_span_triage(base_spans, trial_context)
            
            # Convert BaseSpans to EvidenceSpans
            evidence_spans = self._convert_base_spans_to_evidence_spans(triaged_spans)
            
            # Apply must-hit token filtering and quality filtering
            filtered_spans = self._filter_spans(evidence_spans)
            
            all_evidence_spans.extend(filtered_spans)
        
        return all_evidence_spans
    
    def _get_base_spans_from_document(self, doc_id: str) -> List[BaseSpan]:
        """Get BaseSpans from database for a document using proper external reference mapping."""
        try:
            with get_session() as session:
                # Parse doc_id to get the actual internal doc_id
                internal_doc_id = self._resolve_external_doc_id(session, doc_id)
                
                if internal_doc_id is None:
                    raise ValueError(f"Could not resolve external document ID '{doc_id}' to internal doc_id. Document may not exist in database.")
                
                # Query BaseSpans using the resolved internal doc_id
                base_spans = session.query(BaseSpan).filter(
                    BaseSpan.doc_id == internal_doc_id
                ).all()
                
                return base_spans
                
        except Exception as e:
            print(f"Error: Could not get BaseSpans for document {doc_id}: {e}")
            return []
    
    def _resolve_external_doc_id(self, session, external_doc_id: str) -> Optional[int]:
        """
        Resolve external document ID to internal doc_id using Document table.
        
        Args:
            session: Database session
            external_doc_id: External document ID (e.g., 'ctgov:NCT12345', 'pubmed:12345678')
            
        Returns:
            Internal doc_id (integer) or None if not found
            
        Raises:
            ValueError: If external_doc_id format is invalid
        """
        if not external_doc_id:
            raise ValueError("External document ID cannot be empty")
        
        # Handle different external ID formats
        if ':' in external_doc_id:
            source, identifier = external_doc_id.split(':', 1)
            source = source.lower()
            
            # Map source types to Document table columns
            if source == 'ctgov':
                # Look up by NCT ID
                document = session.query(Document).filter(
                    Document.nct_id == identifier
                ).first()
            elif source == 'pubmed':
                # Look up by PMID
                document = session.query(Document).filter(
                    Document.pmid == identifier
                ).first()
            elif source == 'pmc':
                # Look up by PMCID
                document = session.query(Document).filter(
                    Document.pmcid == identifier
                ).first()
            elif source == 'doi':
                # Look up by DOI
                document = session.query(Document).filter(
                    Document.doi == identifier
                ).first()
            else:
                # For other sources, try to match by source_type and identifier
                # This is a fallback for custom source types
                document = session.query(Document).filter(
                    Document.source_type == source.upper(),
                    Document.source_url.contains(identifier)
                ).first()
        else:
            # If no source prefix, assume it's already an internal doc_id
            try:
                internal_id = int(external_doc_id)
                # Verify the document exists
                document = session.query(Document).filter(
                    Document.doc_id == internal_id
                ).first()
            except ValueError:
                raise ValueError(f"Invalid external document ID format: '{external_doc_id}'. Expected format: 'source:identifier' or integer doc_id")
        
        return document.doc_id if document else None
    
    def _perform_span_triage(self, base_spans: List[BaseSpan], 
                           trial_context: Dict[str, Any]) -> List[BaseSpan]:
        """Perform budgeted span triage with must-hit token reservation using SpanTriageWorker."""
        if not base_spans:
            return []
        
        # Get the first span's doc_id for triage
        doc_id = base_spans[0].doc_id if base_spans else None
        if not doc_id:
            return []
        
        # Determine required fields based on trial context
        required_fields = self._determine_required_fields(trial_context)
        
        # Create must-hit token queries from self.must_hit_tokens
        must_hit_queries = self._create_must_hit_queries()
        
        # Create regular field queries
        field_queries = self._create_field_queries(required_fields, trial_context)
        
        # Combine all queries
        all_queries = must_hit_queries + field_queries
        
        # Perform triage using SpanTriageWorker
        triage_result = self.span_triage.process({
            "doc_id": doc_id,
            "queries": all_queries,
            "required_fields": required_fields
        })
        
        if not triage_result.success:
            print(f"Warning: Span triage failed: {triage_result.error_message}")
            return []
        
        # Extract selected span IDs
        selected_span_ids = set()
        
        # Add must-hit spans (prioritized)
        must_hit_spans = triage_result.output.get("must_hit_spans", {})
        for field_spans in must_hit_spans.values():
            selected_span_ids.update(field_spans)
        
        # Add regular selected spans
        selected_spans = triage_result.output.get("selected_spans", {})
        for field_spans in selected_spans.values():
            selected_span_ids.update(field_spans)
        
        # Convert span IDs back to BaseSpan objects
        span_id_to_span = {span.span_id: span for span in base_spans}
        selected_base_spans = []
        
        # Add must-hit spans first (prioritized)
        for field_spans in must_hit_spans.values():
            for span_id in field_spans:
                if span_id in span_id_to_span:
                    selected_base_spans.append(span_id_to_span[span_id])
        
        # Add regular selected spans
        for field_spans in selected_spans.values():
            for span_id in field_spans:
                if span_id in span_id_to_span and span_id_to_span[span_id] not in selected_base_spans:
                    selected_base_spans.append(span_id_to_span[span_id])
        
        return selected_base_spans
    
    def _perform_bm25_span_triage(self, base_spans: List[BaseSpan], 
                                 required_fields: List[str], 
                                 trial_context: Dict[str, Any]) -> List[BaseSpan]:
        """Perform span triage using BM25 search with field boosts."""
        selected_spans = []
        
        # Create search queries for each required field
        search_queries = self._create_bm25_search_queries(required_fields, trial_context)
        
        for query_info in search_queries:
            query = query_info['query']
            section = query_info.get('section')
            top_k = query_info.get('top_k', 5)
            is_must_hit = query_info.get('must_hit', False)
            
            # Search using BM25
            bm25_results = self.bm25_indexer.search(
                query=query,
                section=section,
                top_k=top_k,
                use_field_boosts=True
            )
            
            # Convert results to BaseSpans
            for result in bm25_results:
                span_id = result['span_id']
                # Find corresponding BaseSpan
                for span in base_spans:
                    if span.span_id == span_id:
                        if is_must_hit:
                            # Prioritize must-hit spans
                            selected_spans.insert(0, span)
                        else:
                            selected_spans.append(span)
                        break
        
        # Remove duplicates while preserving order
        seen_span_ids = set()
        unique_spans = []
        for span in selected_spans:
            if span.span_id not in seen_span_ids:
                seen_span_ids.add(span.span_id)
                unique_spans.append(span)
        
        # Limit to reasonable number of spans
        return unique_spans[:20]  # Limit to top 20 spans
    
    def _determine_required_fields(self, trial_context: Dict[str, Any]) -> List[str]:
        """Determine required fields based on trial context."""
        required_fields = []
        
        # Always include core fields
        required_fields.extend([
            "endpoints", "survival_method", "design_archetype", 
            "analysis_denominators", "response_breakdown"
        ])
        
        # Add disease-specific fields
        disease = trial_context.get("disease", "").lower()
        if "cancer" in disease or "oncology" in disease:
            required_fields.extend(["survival_medians", "recist_criteria"])
        
        # Add intervention-specific fields
        intervention = trial_context.get("intervention", "").lower()
        if "immunotherapy" in intervention:
            required_fields.extend(["immune_response", "pseudo_progression"])
        
        return required_fields
    
    def _create_bm25_search_queries(self, required_fields: List[str], 
                                   trial_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create BM25 search queries for required fields with field boosts."""
        queries = []
        
        # Methods section queries (higher boost)
        if "endpoints" in required_fields:
            queries.extend([
                {
                    "query": "primary endpoint response rate",
                    "section": "Methods",
                    "top_k": 3,
                    "must_hit": True
                },
                {
                    "query": "secondary endpoint progression survival",
                    "section": "Methods", 
                    "top_k": 3,
                    "must_hit": True
                }
            ])
        
        if "survival_method" in required_fields:
            queries.extend([
                {
                    "query": "kaplan meier survival analysis",
                    "section": "Methods",
                    "top_k": 3,
                    "must_hit": True
                },
                {
                    "query": "log rank test cox regression",
                    "section": "Methods",
                    "top_k": 2,
                    "must_hit": False
                }
            ])
        
        if "design_archetype" in required_fields:
            queries.extend([
                {
                    "query": "gehan two stage design",
                    "section": "Methods",
                    "top_k": 2,
                    "must_hit": True
                },
                {
                    "query": "interim analysis stopping rules",
                    "section": "Methods",
                    "top_k": 2,
                    "must_hit": True
                }
            ])
        
        # Results section queries (good boost)
        if "response_breakdown" in required_fields:
            queries.extend([
                {
                    "query": "objective response rate RECIST",
                    "section": "Results",
                    "top_k": 3,
                    "must_hit": True
                },
                {
                    "query": "complete partial stable progressive disease",
                    "section": "Results",
                    "top_k": 3,
                    "must_hit": True
                }
            ])
        
        if "survival_medians" in required_fields:
            queries.extend([
                {
                    "query": "median overall survival",
                    "section": "Results",
                    "top_k": 3,
                    "must_hit": True
                },
                {
                    "query": "median progression free survival",
                    "section": "Results",
                    "top_k": 3,
                    "must_hit": True
                }
            ])
        
        # Add disease-specific queries
        disease = trial_context.get("disease", "").lower()
        if "cancer" in disease or "oncology" in disease:
            queries.extend([
                {
                    "query": "tumor response assessment",
                    "section": "Results",
                    "top_k": 2,
                    "must_hit": False
                }
            ])
        
        # Add intervention-specific queries
        intervention = trial_context.get("intervention", "").lower()
        if "immunotherapy" in intervention:
            queries.extend([
                {
                    "query": "immune response pseudo progression",
                    "section": "Results",
                    "top_k": 2,
                    "must_hit": False
                }
            ])
        
        return queries
    
    def _convert_base_spans_to_evidence_spans(self, base_spans: List[BaseSpan]) -> List[EvidenceSpan]:
        """Convert BaseSpans to EvidenceSpans."""
        evidence_spans = []
        
        for base_span in base_spans:
            # Create EvidenceSpan from BaseSpan
            evidence_span = EvidenceSpan(
                doc_id=base_span.doc_id,
                quote=base_span.text,  # Use original text for better alignment
                section=base_span.section,
                page=base_span.page,
                char_start=base_span.char_start,
                char_end=base_span.char_end,
                confidence=0.9,  # High confidence for BaseSpans
                kind="base",  # Base spans from ingestion
                table_id=base_span.table_id,
                table_row=base_span.row,  # Include table row position
                table_col=base_span.col   # Include table column position
            )
            
            # Set proper span references
            # Use span_id as the canonical external identifier
            # Store numeric BaseSpan ID for downstream joins
            evidence_span.span_ids = [base_span.span_id]
            
            evidence_spans.append(evidence_span)
        
        return evidence_spans
    
    def _filter_spans(self, spans: List[EvidenceSpan]) -> List[EvidenceSpan]:
        """Filter spans based on quality criteria and must-hit token requirements."""
        filtered = []
        
        for span in spans:
            # Check confidence threshold
            if span.confidence < self.min_confidence:
                continue
            
            # Check span length
            if len(span.quote) > self.max_span_length:
                continue
            
            # Check span coordinates
            if not validate_span_coordinates(span.page, span.char_start, span.char_end):
                continue
            
            # Check for low-quality indicators
            if self._is_low_quality_span(span):
                continue
            
            # Check for must-hit tokens (reserve slots for critical content)
            if self._contains_must_hit_tokens(span):
                # Prioritize spans with must-hit tokens
                span.confidence = min(1.0, span.confidence + 0.1)
            
            filtered.append(span)
        
        return filtered
    
    def _contains_must_hit_tokens(self, span: EvidenceSpan) -> bool:
        """Check if span contains must-hit tokens for critical fields."""
        text_lower = span.quote.lower()
        
        for field, tokens in self.must_hit_tokens.items():
            for token in tokens:
                if token.lower() in text_lower:
                    return True
        
        return False
    
    def _is_low_quality_span(self, span: EvidenceSpan) -> bool:
        """Check if a span is low quality."""
        text = span.quote.lower()
        
        # Check for common low-quality indicators
        low_quality_indicators = [
            "page", "figure", "table", "reference", "citation",
            "supplementary", "appendix", "footnote", "header", "footer"
        ]
        
        for indicator in low_quality_indicators:
            if indicator in text:
                return True
        
        # Check for very short spans
        if len(span.quote.strip()) < 20:
            return True
        
        # Check for spans with mostly numbers/symbols
        alphanumeric_chars = sum(1 for c in span.quote if c.isalnum())
        if alphanumeric_chars / len(span.quote) < 0.3:
            return True
        
        return False
    
    def _create_must_hit_queries(self) -> List[TriageQuery]:
        """Create must-hit token queries from self.must_hit_tokens using normalized sections."""
        from ..section_normalizer import NormalizedSection
        
        queries = []
        for field_name, tokens in self.must_hit_tokens.items():
            for token in tokens:
                queries.append(TriageQuery(
                    field_name=f"must_hit_{field_name}_{token}",
                    query_text=token,
                    section=NormalizedSection.RESULTS,  # Use normalized section enum
                    priority=2,  # Higher priority for must-hit tokens
                    must_fill=True  # Mark as must-fill
                ))
        return queries
    
    def _create_field_queries(self, required_fields: List[str], 
                              trial_context: Dict[str, Any]) -> List[TriageQuery]:
        """Create field queries for SpanTriageWorker using normalized sections and config-driven synonyms."""
        from ..query_synonym_manager import QuerySynonymManager
        
        queries = []
        synonym_manager = QuerySynonymManager()
        
        # Extract context for synonym generation
        disease = trial_context.get("disease", "").lower()
        intervention = trial_context.get("intervention", "")
        
        # Methods section queries
        if "endpoints" in required_fields:
            # Get disease-specific synonyms for endpoints
            disease_terms = synonym_manager.get_disease_synonyms(disease, "primary_terms")
            endpoint_terms = synonym_manager.get_endpoint_synonyms("primary_endpoint", "response_rate")
            
            # Combine terms for more comprehensive queries
            primary_query = " ".join(disease_terms[:2] + endpoint_terms[:2]) if disease_terms and endpoint_terms else "primary endpoint response rate"
            secondary_query = " ".join(disease_terms[:2] + ["secondary endpoint", "progression", "survival"]) if disease_terms else "secondary endpoint progression survival"
            
            queries.extend([
                TriageQuery("endpoints_primary", primary_query, "Methods", 1, True),
                TriageQuery("endpoints_secondary", secondary_query, "Methods", 1, True)
            ])
        
        if "survival_method" in required_fields:
            # Get method-specific synonyms
            kaplan_terms = synonym_manager.get_method_synonyms("survival_analysis", "kaplan_meier")
            logrank_terms = synonym_manager.get_method_synonyms("survival_analysis", "log_rank")
            
            kaplan_query = " ".join(kaplan_terms) if kaplan_terms else "Kaplan-Meier survival analysis"
            logrank_query = " ".join(logrank_terms) if logrank_terms else "log-rank test Cox regression"
            
            queries.extend([
                TriageQuery("kaplan_meier", kaplan_query, "Methods", 1, True),
                TriageQuery("log_rank", logrank_query, "Methods", 1, False)
            ])
        
        if "design_archetype" in required_fields:
            # Get design-specific synonyms
            gehan_terms = synonym_manager.get_method_synonyms("study_design", "gehan_design")
            interim_terms = synonym_manager.get_method_synonyms("study_design", "interim_analysis")
            
            gehan_query = " ".join(gehan_terms) if gehan_terms else "Gehan two-stage design"
            interim_query = " ".join(interim_terms) if interim_terms else "interim analysis stopping rules"
            
            queries.extend([
                TriageQuery("gehan_design", gehan_query, "Methods", 1, True),
                TriageQuery("interim_looks", interim_query, "Methods", 1, False)
            ])
        
        # Results section queries
        if "response_breakdown" in required_fields:
            # Get disease-specific response terms
            response_terms = synonym_manager.get_disease_synonyms(disease, "response_terms")
            endpoint_terms = synonym_manager.get_endpoint_synonyms("primary_endpoint", "response_rate")
            
            orr_query = " ".join(response_terms[:2] + endpoint_terms[:2]) if response_terms and endpoint_terms else "overall response rate RECIST"
            breakdown_query = " ".join(response_terms[:2] + ["complete", "partial", "stable", "progressive"]) if response_terms else "complete partial stable progressive disease"
            
            queries.extend([
                TriageQuery("orr_recist", orr_query, "Results", 1, True),
                TriageQuery("response_breakdown", breakdown_query, "Results", 1, False)
            ])
        
        if "survival_medians" in required_fields:
            # Get disease-specific survival terms
            survival_terms = synonym_manager.get_disease_synonyms(disease, "survival_terms")
            endpoint_terms = synonym_manager.get_endpoint_synonyms("primary_endpoint", "survival")
            
            os_query = " ".join(survival_terms[:2] + ["overall survival"]) if survival_terms else "median overall survival"
            pfs_query = " ".join(survival_terms[:2] + ["progression free survival"]) if survival_terms else "median progression free survival"
            
            queries.extend([
                TriageQuery("median_os", os_query, "Results", 1, True),
                TriageQuery("median_pfs", pfs_query, "Results", 1, True)
            ])
        
        return queries
    
    def get_retrieval_stats(self) -> Dict[str, Any]:
        """Get retrieval-specific statistics."""
        base_stats = self.get_stats()
        base_stats.update({
            "max_span_length": self.max_span_length,
            "min_confidence": self.min_confidence,
            "uses_basespans": True,
            "enforces_budgets": True,
            "reserves_must_hit_tokens": True,
            "must_hit_token_fields": list(self.must_hit_tokens.keys()),
            "span_triage_integrated": True,
            "bm25_indexer_used": True,
            "bm25_index_stats": self.bm25_indexer.get_index_stats()
        })
        return base_stats
