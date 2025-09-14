"""
Deterministic synthesis for trials that pass early stopping and full review.
Generates fully-cited narratives using only structured data from Study Cards.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
import yaml
from pydantic import BaseModel

from ncfd.db.models import Study, Trial
from ncfd.signals.gates import GateResult
from ncfd.signals.scoring import ScoreResult


class Ref(BaseModel):
    """Reference to a specific field in a study card."""
    study_id: str
    field_path: str
    span: Optional[str] = None  # e.g., "p3" or "fig2"


class Sentence(BaseModel):
    """A sentence with its supporting references."""
    text: str
    refs: List[Ref]


class SynthesisDoc(BaseModel):
    """Complete synthesis document for a trial."""
    trial_id: str
    nct_id: str
    text: str
    sections: Dict[str, List[Sentence]]
    citations: List[Dict[str, Any]]
    quality: Dict[str, Any]
    audit: Dict[str, Any]
    gpt5_hook_triggered: bool = False


@dataclass
class SynthesisConfig:
    """Configuration for deterministic synthesis."""
    field_precedence: Dict[str, List[str]]
    severity_buckets: Dict[str, Tuple[float, float]]
    gate_templates: Dict[str, str]
    coverage_requirements: Dict[str, List[str]]
    max_tokens: int = 2000
    max_sentences_per_section: int = 10
    gpt5_threshold: float = 0.85  # P_fail threshold to trigger GPT-5 thinking
    require_references: bool = True
    min_study_cards: int = 1
    max_missing_fields: int = 2


class SynthesisError(Exception):
    """Raised when synthesis cannot proceed due to missing requirements."""
    pass


class EvidenceConstrainedSynthesizer:
    """Evidence-constrained synthesis engine with early stopping enforcement."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
    
    def _load_config(self, config_path: Optional[str]) -> SynthesisConfig:
        """Load synthesis configuration."""
        if config_path is None:
            config_path = "config/det_synthesis.yaml"
        
        config_file = Path(config_path)
        if not config_file.exists():
            # Default configuration
            return SynthesisConfig(
                field_precedence={
                    "primary_endpoint": ["Registry", "Paper", "FDA", "PR", "Abstract"],
                    "n_total": ["Registry", "Paper", "PR", "Abstract"],
                    "effect_primary": ["Paper", "PR", "Registry", "Abstract"],
                    "p_value": ["Paper", "PR", "Registry", "Abstract"],
                    "itt_status": ["Paper", "PR", "Registry", "Abstract"],
                    "dropout_missing_itt_pct": ["Paper", "PR", "Registry", "Abstract"],
                    "interim_looks": ["Registry", "Paper", "PR", "Abstract"],
                    "alpha_spending": ["Registry", "Paper", "PR", "Abstract"],
                    "subgroup_multiplicity": ["Paper", "PR", "Registry", "Abstract"],
                },
                severity_buckets={
                    "critical": (0.90, 1.00),
                    "high": (0.80, 0.90),
                    "medium": (0.60, 0.80),
                    "low": (0.40, 0.60),
                },
                gate_templates={
                    "G1": "Alpha-Meltdown: endpoint changed post-registration and trial is underpowered.",
                    "G2": "Analysis-Gaming: subgroup-only win without multiplicity; ITT neutral with dropout asymmetry.",
                    "G3": "Plausibility: claimed effect exceeds class priors with weak design (single-arm or multiple looks).",
                    "G4": "p-Hacking: p-value near 0.05 alongside endpoint/subgroup shifts.",
                },
                coverage_requirements={
                    "pivotal": [
                        "primary_endpoint",
                        "n_total", 
                        "itt_status",
                        "effect_primary_or_p_value"
                    ]
                }
            )
        
        with open(config_file) as f:
            data = yaml.safe_load(f)
        
        return SynthesisConfig(**data)
    
    def _validate_early_stopping_requirements(
        self, 
        study_cards: List[Study], 
        gates: Dict[str, GateResult],
        score: ScoreResult
    ) -> None:
        """Validate that trial meets early stopping requirements."""
        # Must have study cards (full review completed)
        if not study_cards:
            raise SynthesisError(
                f"No study cards found. Trial must complete full literature review before synthesis."
            )
        
        # Must have fired gates (early stopping should have caught robust trials)
        fired_gates = [g for g in gates.values() if g.fired]
        if not fired_gates:
            raise SynthesisError(
                f"No gates fired (P_fail={score.p_fail:.3f}). "
                f"Early stopping should have filtered out robust trials. "
                f"Check literature review early stopping logic."
            )
        
        # Check coverage requirements for pivotal trials
        if self._is_pivotal_trial(study_cards):
            missing_fields = self._check_coverage_requirements(study_cards)
            if missing_fields:
                raise SynthesisError(
                    f"Missing required fields for pivotal trial: {missing_fields}. "
                    f"Full review incomplete."
                )
    
    def _is_pivotal_trial(self, study_cards: List[Study]) -> bool:
        """Determine if this is a pivotal trial based on study cards."""
        for card in study_cards:
            extracted = card.extracted_jsonb or {}
            if extracted.get("is_pivotal", False):
                return True
            # Check phase from registry
            if extracted.get("phase") in ["3", "III", "pivotal"]:
                return True
        return False
    
    def _check_coverage_requirements(self, study_cards: List[Study]) -> List[str]:
        """Check if required fields are present."""
        required_fields = self.config.coverage_requirements.get("pivotal", [])
        missing = []
        
        for field in required_fields:
            if field == "effect_primary_or_p_value":
                # Special case: either effect or p-value is acceptable
                has_effect = any(
                    card.extracted_jsonb and 
                    (card.extracted_jsonb.get("effect_primary") or card.extracted_jsonb.get("p_value"))
                    for card in study_cards
                )
                if not has_effect:
                    missing.append("effect_primary_or_p_value")
            else:
                has_field = any(
                    card.extracted_jsonb and field in card.extracted_jsonb
                    for card in study_cards
                )
                if not has_field:
                    missing.append(field)
        
        return missing
    
    def _resolve_field_with_precedence(
        self, 
        study_cards: List[Study], 
        field: str, 
        precedence: List[str]
    ) -> Tuple[Optional[Any], Optional[str], Optional[str]]:
        """Resolve field value using precedence order."""
        for doc_type in precedence:
            for card in study_cards:
                if card.doc_type == doc_type and card.extracted_jsonb:
                    if field in card.extracted_jsonb:
                        val = card.extracted_jsonb[field]
                        # Get evidence span if available
                        spans = card.extracted_jsonb.get("evidence_spans", {}) or {}
                        span = spans.get(field)
                        return val, card.study_id, span
        return None, None, None
    
    def _build_overview_section(
        self, 
        trial: Trial, 
        study_cards: List[Study]
    ) -> List[Sentence]:
        """Build trial overview section."""
        sentences = []
        
        # Trial identification
        trial_text = f"Trial {trial.nct_id} ({trial.phase}) in {trial.indication}"
        refs = []
        
        # Get sponsor info
        sponsor_val, sponsor_study_id, sponsor_span = self._resolve_field_with_precedence(
            study_cards, "sponsor", ["Registry", "PR", "Paper", "Abstract"]
        )
        if sponsor_val:
            trial_text += f" sponsored by {sponsor_val}"
            refs.append(Ref(study_id=sponsor_study_id, field_path="sponsor", span=sponsor_span))
        
        # Get completion date
        completion_val, completion_study_id, completion_span = self._resolve_field_with_precedence(
            study_cards, "est_primary_completion_date", ["Registry", "PR", "Paper", "Abstract"]
        )
        if completion_val:
            trial_text += f" with expected completion {completion_val}"
            refs.append(Ref(study_id=completion_study_id, field_path="est_primary_completion_date", span=completion_span))
        
        trial_text += "."
        sentences.append(Sentence(text=trial_text, refs=refs))
        
        return sentences
    
    def _build_design_section(self, study_cards: List[Study]) -> List[Sentence]:
        """Build trial design section."""
        sentences = []
        
        # Primary endpoint
        endpoint_val, endpoint_study_id, endpoint_span = self._resolve_field_with_precedence(
            study_cards, "primary_endpoint", self.config.field_precedence["primary_endpoint"]
        )
        if endpoint_val:
            endpoint_text = f"Primary endpoint: {endpoint_val}"
            refs = [Ref(study_id=endpoint_study_id, field_path="primary_endpoint", span=endpoint_span)]
            sentences.append(Sentence(text=endpoint_text, refs=refs))
        
        # Sample size
        n_val, n_study_id, n_span = self._resolve_field_with_precedence(
            study_cards, "n_total", self.config.field_precedence["n_total"]
        )
        if n_val:
            n_text = f"Sample size: {n_val} patients"
            refs = [Ref(study_id=n_study_id, field_path="n_total", span=n_span)]
            sentences.append(Sentence(text=n_text, refs=refs))
        
        # Randomization/blinding
        rand_val, rand_study_id, rand_span = self._resolve_field_with_precedence(
            study_cards, "randomization", ["Registry", "Paper", "PR", "Abstract"]
        )
        if rand_val:
            rand_text = f"Design: {rand_val}"
            refs = [Ref(study_id=rand_study_id, field_path="randomization", span=rand_span)]
            sentences.append(Sentence(text=rand_text, refs=refs))
        
        return sentences
    
    def _build_results_section(self, study_cards: List[Study]) -> List[Sentence]:
        """Build results section."""
        sentences = []
        
        # Primary results
        effect_val, effect_study_id, effect_span = self._resolve_field_with_precedence(
            study_cards, "effect_primary", self.config.field_precedence["effect_primary"]
        )
        p_val, p_study_id, p_span = self._resolve_field_with_precedence(
            study_cards, "p_value", self.config.field_precedence["p_value"]
        )
        
        if effect_val or p_val:
            results_text = "Primary results: "
            refs = []
            
            if effect_val:
                results_text += f"effect size {effect_val}"
                refs.append(Ref(study_id=effect_study_id, field_path="effect_primary", span=effect_span))
            
            if p_val:
                if effect_val:
                    results_text += ", "
                results_text += f"p-value {p_val}"
                refs.append(Ref(study_id=p_study_id, field_path="p_value", span=p_span))
            
            results_text += "."
            sentences.append(Sentence(text=results_text, refs=refs))
        else:
            sentences.append(Sentence(
                text="Primary results not yet disclosed.",
                refs=[]
            ))
        
        return sentences
    
    def _build_red_flags_section(
        self, 
        gates: Dict[str, GateResult],
        study_cards: List[Study]
    ) -> List[Sentence]:
        """Build red flags section from fired gates."""
        sentences = []
        
        fired_gates = [g for g in gates.values() if g.fired]
        
        if not fired_gates:
            sentences.append(Sentence(
                text="No co-dependent gates fired.",
                refs=[]
            ))
            return sentences
        
        # List fired gates with evidence
        for gate in fired_gates:
            gate_text = self.config.gate_templates.get(gate.id, f"Gate {gate.id} fired")
            refs = []
            
            # Add references from supporting signals
            for signal_id in gate.supporting_signals:
                # Find the signal's evidence in study cards
                for card in study_cards:
                    if card.extracted_jsonb and signal_id in card.extracted_jsonb.get("signals", {}):
                        signal_data = card.extracted_jsonb["signals"][signal_id]
                        if "evidence_span" in signal_data:
                            refs.append(Ref(
                                study_id=card.study_id,
                                field_path=f"signals.{signal_id}",
                                span=signal_data["evidence_span"]
                            ))
            
            sentences.append(Sentence(text=gate_text, refs=refs))
        
        return sentences
    
    def _build_posterior_section(self, score: ScoreResult) -> List[Sentence]:
        """Build posterior probability section."""
        if score.stop_rule_applied is not None:
            text = f"Stop rule applied: P_fail set to {score.p_fail:.3f}."
        else:
            text = f"Posterior P_fail = {score.p_fail:.3f} (prior {score.prior_pi:.3f}; LRs from fired gates)."
        
        return [Sentence(text=text, refs=[])]
    
    def _build_coverage_gaps_section(self, study_cards: List[Study]) -> List[Sentence]:
        """Build coverage gaps section."""
        sentences = []
        
        # Check for missing fields
        missing_fields = []
        for field in ["effect_primary", "p_value", "itt_status", "dropout_missing_itt_pct"]:
            has_field = any(
                card.extracted_jsonb and field in card.extracted_jsonb
                for card in study_cards
            )
            if not has_field:
                missing_fields.append(field)
        
        if missing_fields:
            text = f"Coverage gaps: missing {', '.join(missing_fields)}."
            sentences.append(Sentence(text=text, refs=[]))
        else:
            sentences.append(Sentence(text="All required fields covered.", refs=[]))
        
        return sentences
    
    def _build_sources_section(self, study_cards: List[Study]) -> List[Sentence]:
        """Build sources section."""
        sentences = []
        
        for card in study_cards:
            source_text = f"{card.study_id}: {card.doc_type} ({card.year})"
            if card.url:
                source_text += f" - {card.url}"
            sentences.append(Sentence(text=source_text, refs=[]))
        
        return sentences
    
    def _should_trigger_gpt5_hook(self, score: ScoreResult) -> bool:
        """Determine if GPT-5 thinking model should be triggered."""
        return score.p_fail >= self.config.gpt5_threshold
    
    def _validate_synthesis_doc(self, doc: SynthesisDoc) -> None:
        """Validate that every sentence has at least one reference."""
        # Sections that don't require references
        no_ref_sections = {"posterior", "coverage_gaps", "sources", "red_flags"}
        
        for section_name, sentences in doc.sections.items():
            for i, sentence in enumerate(sentences):
                if not sentence.refs and section_name not in no_ref_sections:
                    raise ValueError(
                        f"Section '{section_name}', sentence {i}: '{sentence.text}' has no references"
                    )
    
    def generate(
        self,
        trial: Trial,
        study_cards: List[Study],
        gates: Dict[str, GateResult],
        score: ScoreResult
    ) -> SynthesisDoc:
        """
        Generate deterministic synthesis for a trial.
        
        Args:
            trial: Trial metadata
            study_cards: List of study cards from full review
            gates: Gate results from signal analysis
            score: Scoring result
            
        Returns:
            SynthesisDoc with fully-cited narrative
            
        Raises:
            SynthesisError: If early stopping requirements not met
        """
        # Validate early stopping requirements
        self._validate_early_stopping_requirements(study_cards, gates, score)
        
        # Check if GPT-5 hook should be triggered
        gpt5_hook_triggered = self._should_trigger_gpt5_hook(score)
        
        # Build sections
        sections = {
            "overview": self._build_overview_section(trial, study_cards),
            "design": self._build_design_section(study_cards),
            "results": self._build_results_section(study_cards),
            "red_flags": self._build_red_flags_section(gates, study_cards),
            "posterior": self._build_posterior_section(score),
            "coverage_gaps": self._build_coverage_gaps_section(study_cards),
            "sources": self._build_sources_section(study_cards)
        }
        
        # Combine all text
        all_text = ""
        citations = []
        sentence_idx = 0
        
        for section_name, section_sentences in sections.items():
            if section_sentences:
                all_text += f"\n\n{section_name.title()}:\n"
                for sentence in section_sentences:
                    all_text += sentence.text + " "
                    citations.append({
                        "sentence_idx": sentence_idx,
                        "refs": [ref.model_dump() for ref in sentence.refs]
                    })
                    sentence_idx += 1
        
        # Build quality assessment
        quality = {
            "coverage_level": "high" if len(study_cards) >= 3 else "medium" if len(study_cards) >= 1 else "low",
            "study_card_count": len(study_cards),
            "fired_gates_count": len([g for g in gates.values() if g.fired])
        }
        
        # Build audit trail
        audit = {
            "fired_signals": [s for g in gates.values() if g.fired for s in g.supporting_signals],
            "fired_gates": [g_id for g_id, g in gates.items() if g.fired],
            "prior_pi": score.prior_pi,
            "posterior_p_fail": score.p_fail,
            "stop_rule_applied": score.stop_rule_applied
        }
        
        # Create synthesis document
        doc = SynthesisDoc(
            trial_id=trial.trial_id,
            nct_id=trial.nct_id,
            text=all_text.strip(),
            sections=sections,
            citations=citations,
            quality=quality,
            audit=audit,
            gpt5_hook_triggered=gpt5_hook_triggered
        )
        
        # Validate the document
        self._validate_synthesis_doc(doc)
        
        return doc


# Import the new independent LLM analysis
from .independent_llm_analysis import IndependentLLMAnalysis, trigger_independent_llm_analysis_sync
