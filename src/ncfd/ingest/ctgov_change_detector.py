"""
Change detection system for ClinicalTrials.gov trials.

This module identifies meaningful changes between trial versions that may
trigger signal evaluation and risk assessment updates.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .ctgov_types import (
    ComprehensiveTrialFields, Change, TrialChangeSummary,
    TrialPhase, TrialStatus, InterventionType
)

logger = logging.getLogger(__name__)


@dataclass
class ChangeDetectionConfig:
    """Configuration for change detection."""
    # Fields that trigger HIGH significance changes
    high_significance_fields: List[str] = None
    
    # Fields that trigger MEDIUM significance changes
    medium_significance_fields: List[str] = None
    
    # Fields that trigger LOW significance changes
    low_significance_fields: List[str] = None
    
    # Minimum change threshold for numeric fields
    numeric_change_threshold: float = 0.1  # 10%
    
    # Text similarity threshold for text fields
    text_similarity_threshold: float = 0.8
    
    def __post_init__(self):
        """Set default field significance levels."""
        if self.high_significance_fields is None:
            self.high_significance_fields = [
                "primary_endpoint_text",
                "sample_size",
                "analysis_plan_text",
                "phase",
                "status",
                "trial_design.allocation",
                "trial_design.masking",
                "statistical_analysis.alpha_level",
                "statistical_analysis.power"
            ]
        
        if self.medium_significance_fields is None:
            self.medium_significance_fields = [
                "sponsor_info.lead_sponsor_name",
                "interventions",
                "conditions",
                "enrollment_info.count",
                "locations",
                "study_start_date",
                "primary_completion_date"
            ]
        
        if self.low_significance_fields is None:
            self.low_significance_fields = [
                "brief_title",
                "official_title",
                "acronym",
                "keywords",
                "mesh_terms",
                "eligibility_criteria"
            ]


class CtgovChangeDetector:
    """Detects changes between CT.gov trial versions."""
    
    def __init__(self, config: Optional[ChangeDetectionConfig] = None):
        """Initialize the change detector."""
        self.config = config or ChangeDetectionConfig()
        self.logger = logging.getLogger(__name__)
    
    def detect_changes(
        self, 
        old_trial: ComprehensiveTrialFields, 
        new_trial: ComprehensiveTrialFields
    ) -> TrialChangeSummary:
        """
        Detect changes between two trial versions.
        
        Args:
            old_trial: Previous version of the trial
            new_trial: Current version of the trial
            
        Returns:
            TrialChangeSummary with detected changes
        """
        if old_trial.nct_id != new_trial.nct_id:
            raise ValueError("Cannot compare trials with different NCT IDs")
        
        changes = []
        
        # Detect changes in basic fields
        changes.extend(self._detect_basic_field_changes(old_trial, new_trial))
        
        # Detect changes in sponsor information
        changes.extend(self._detect_sponsor_changes(old_trial, new_trial))
        
        # Detect changes in trial design
        changes.extend(self._detect_trial_design_changes(old_trial, new_trial))
        
        # Detect changes in interventions
        changes.extend(self._detect_intervention_changes(old_trial, new_trial))
        
        # Detect changes in outcomes
        changes.extend(self._detect_outcome_changes(old_trial, new_trial))
        
        # Detect changes in enrollment
        changes.extend(self._detect_enrollment_changes(old_trial, new_trial))
        
        # Detect changes in statistical analysis
        changes.extend(self._detect_statistical_changes(old_trial, new_trial))
        
        # Detect changes in dates
        changes.extend(self._detect_date_changes(old_trial, new_trial))
        
        # Detect changes in locations
        changes.extend(self._detect_location_changes(old_trial, new_trial))
        
        # Create change summary
        summary = TrialChangeSummary(
            nct_id=old_trial.nct_id,
            version_from=getattr(old_trial, 'version_id', 'unknown'),
            version_to=getattr(new_trial, 'version_id', 'unknown'),
            changes=changes,
            detected_at=datetime.utcnow()
        )
        
        self.logger.info(
            f"Detected {summary.change_count} changes for trial {old_trial.nct_id}, "
            f"{summary.significant_change_count} significant"
        )
        
        return summary
    
    def _detect_basic_field_changes(
        self, 
        old_trial: ComprehensiveTrialFields, 
        new_trial: ComprehensiveTrialFields
    ) -> List[Change]:
        """Detect changes in basic trial fields."""
        changes = []
        
        # Check title changes
        if old_trial.brief_title != new_trial.brief_title:
            changes.append(Change(
                field_name="brief_title",
                old_value=old_trial.brief_title,
                new_value=new_trial.brief_title,
                change_type="MODIFIED",
                significance=self._get_field_significance("brief_title"),
                description="Brief title changed"
            ))
        
        # Check phase changes
        if old_trial.phase != new_trial.phase:
            changes.append(Change(
                field_name="phase",
                old_value=old_trial.phase.value if old_trial.phase else None,
                new_value=new_trial.phase.value if new_trial.phase else None,
                change_type="MODIFIED",
                significance="HIGH",
                description="Trial phase changed"
            ))
        
        # Check status changes
        if old_trial.status != new_trial.status:
            changes.append(Change(
                field_name="status",
                old_value=old_trial.status.value if old_trial.status else None,
                new_value=new_trial.status.value if new_trial.status else None,
                change_type="MODIFIED",
                significance="HIGH",
                description="Trial status changed"
            ))
        
        return changes
    
    def _detect_sponsor_changes(
        self, 
        old_trial: ComprehensiveTrialFields, 
        new_trial: ComprehensiveTrialFields
    ) -> List[Change]:
        """Detect changes in sponsor information."""
        changes = []
        
        old_sponsor = old_trial.sponsor_info
        new_sponsor = new_trial.sponsor_info
        
        # Check lead sponsor name changes
        if old_sponsor.lead_sponsor_name != new_sponsor.lead_sponsor_name:
            changes.append(Change(
                field_name="sponsor_info.lead_sponsor_name",
                old_value=old_sponsor.lead_sponsor_name,
                new_value=new_sponsor.lead_sponsor_name,
                change_type="MODIFIED",
                significance="MEDIUM",
                description="Lead sponsor name changed"
            ))
        
        # Check collaborator changes
        old_collabs = set(old_sponsor.collaborators)
        new_collabs = set(new_sponsor.collaborators)
        
        added_collabs = new_collabs - old_collabs
        removed_collabs = old_collabs - new_collabs
        
        if added_collabs:
            changes.append(Change(
                field_name="sponsor_info.collaborators",
                old_value=list(old_collabs),
                new_value=list(new_collabs),
                change_type="MODIFIED",
                significance="MEDIUM",
                description=f"Collaborators added: {list(added_collabs)}"
            ))
        
        if removed_collabs:
            changes.append(Change(
                field_name="sponsor_info.collaborators",
                old_value=list(old_collabs),
                new_value=list(new_collabs),
                change_type="MODIFIED",
                significance="MEDIUM",
                description=f"Collaborators removed: {list(removed_collabs)}"
            ))
        
        return changes
    
    def _detect_trial_design_changes(
        self, 
        old_trial: ComprehensiveTrialFields, 
        new_trial: ComprehensiveTrialFields
    ) -> List[Change]:
        """Detect changes in trial design."""
        changes = []
        
        old_design = old_trial.trial_design
        new_design = new_trial.trial_design
        
        # Check allocation changes
        if old_design.allocation != new_design.allocation:
            changes.append(Change(
                field_name="trial_design.allocation",
                old_value=old_design.allocation,
                new_value=new_design.allocation,
                change_type="MODIFIED",
                significance="HIGH",
                description="Trial allocation method changed"
            ))
        
        # Check masking changes
        if old_design.masking != new_design.masking:
            changes.append(Change(
                field_name="trial_design.masking",
                old_value=old_design.masking,
                new_value=new_design.masking,
                change_type="MODIFIED",
                significance="HIGH",
                description="Trial masking/blinding changed"
            ))
        
        return changes
    
    def _detect_intervention_changes(
        self, 
        old_trial: ComprehensiveTrialFields, 
        new_trial: ComprehensiveTrialFields
    ) -> List[Change]:
        """Detect changes in interventions."""
        changes = []
        
        old_interventions = {i.name: i for i in old_trial.interventions}
        new_interventions = {i.name: i for i in new_trial.interventions}
        
        # Check for added interventions
        for name, intervention in new_interventions.items():
            if name not in old_interventions:
                changes.append(Change(
                    field_name="interventions",
                    old_value=None,
                    new_value=intervention.name,
                    change_type="ADDED",
                    significance="MEDIUM",
                    description=f"New intervention added: {intervention.name}"
                ))
        
        # Check for removed interventions
        for name, intervention in old_interventions.items():
            if name not in new_interventions:
                changes.append(Change(
                    field_name="interventions",
                    old_value=intervention.name,
                    new_value=None,
                    change_type="REMOVED",
                    significance="MEDIUM",
                    description=f"Intervention removed: {intervention.name}"
                ))
        
        # Check for modified interventions
        for name in old_interventions.keys() & new_interventions.keys():
            old_int = old_interventions[name]
            new_int = new_interventions[name]
            
            if old_int.type != new_int.type:
                changes.append(Change(
                    field_name=f"interventions.{name}.type",
                    old_value=old_int.type.value,
                    new_value=new_int.type.value,
                    change_type="MODIFIED",
                    significance="MEDIUM",
                    description=f"Intervention type changed for {name}"
                ))
        
        return changes
    
    def _detect_outcome_changes(
        self, 
        old_trial: ComprehensiveTrialFields, 
        new_trial: ComprehensiveTrialFields
    ) -> List[Change]:
        """Detect changes in outcomes."""
        changes = []
        
        # Check primary endpoint changes
        old_primary = self._extract_endpoint_text(old_trial.primary_outcomes)
        new_primary = self._extract_endpoint_text(new_trial.primary_outcomes)
        
        if old_primary != new_primary:
            changes.append(Change(
                field_name="primary_endpoint_text",
                old_value=old_primary,
                new_value=new_primary,
                change_type="MODIFIED",
                significance="HIGH",
                description="Primary endpoint changed"
            ))
        
        return changes
    
    def _detect_enrollment_changes(
        self, 
        old_trial: ComprehensiveTrialFields, 
        new_trial: ComprehensiveTrialFields
    ) -> List[Change]:
        """Detect changes in enrollment information."""
        changes = []
        
        old_enrollment = old_trial.enrollment_info
        new_enrollment = new_trial.enrollment_info
        
        # Check sample size changes
        if old_enrollment.count != new_enrollment.count:
            if old_enrollment.count and new_enrollment.count:
                change_pct = abs(new_enrollment.count - old_enrollment.count) / old_enrollment.count
                if change_pct >= self.config.numeric_change_threshold:
                    changes.append(Change(
                        field_name="enrollment_info.count",
                        old_value=old_enrollment.count,
                        new_value=new_enrollment.count,
                        change_type="MODIFIED",
                        significance="MEDIUM",
                        description=f"Sample size changed by {change_pct:.1%}"
                    ))
            else:
                changes.append(Change(
                    field_name="enrollment_info.count",
                    old_value=old_enrollment.count,
                    new_value=new_enrollment.count,
                    change_type="MODIFIED",
                    significance="MEDIUM",
                    description="Sample size information changed"
                ))
        
        return changes
    
    def _detect_statistical_changes(
        self, 
        old_trial: ComprehensiveTrialFields, 
        new_trial: ComprehensiveTrialFields
    ) -> List[Change]:
        """Detect changes in statistical analysis."""
        changes = []
        
        old_stats = old_trial.statistical_analysis
        new_stats = new_trial.statistical_analysis
        
        # Check alpha level changes
        if old_stats.alpha_level != new_stats.alpha_level:
            changes.append(Change(
                field_name="statistical_analysis.alpha_level",
                old_value=old_stats.alpha_level,
                new_value=new_stats.alpha_level,
                change_type="MODIFIED",
                significance="HIGH",
                description="Alpha level changed"
            ))
        
        # Check power changes
        if old_stats.power != new_stats.power:
            if old_stats.power and new_stats.power:
                change_pct = abs(new_stats.power - old_stats.power) / old_stats.power
                if change_pct >= self.config.numeric_change_threshold:
                    changes.append(Change(
                        field_name="statistical_analysis.power",
                        old_value=old_stats.power,
                        new_value=new_stats.power,
                        change_type="MODIFIED",
                        significance="HIGH",
                        description=f"Statistical power changed by {change_pct:.1%}"
                    ))
        
        return changes
    
    def _detect_date_changes(
        self, 
        old_trial: ComprehensiveTrialFields, 
        new_trial: ComprehensiveTrialFields
    ) -> List[Change]:
        """Detect changes in trial dates."""
        changes = []
        
        # Check study start date changes
        if old_trial.study_start_date != new_trial.study_start_date:
            changes.append(Change(
                field_name="study_start_date",
                old_value=old_trial.study_start_date,
                new_value=new_trial.study_start_date,
                change_type="MODIFIED",
                significance="MEDIUM",
                description="Study start date changed"
            ))
        
        # Check primary completion date changes
        if old_trial.primary_completion_date != new_trial.primary_completion_date:
            changes.append(Change(
                field_name="primary_completion_date",
                old_value=old_trial.primary_completion_date,
                new_value=new_trial.primary_completion_date,
                change_type="MODIFIED",
                significance="MEDIUM",
                description="Primary completion date changed"
            ))
        
        return changes
    
    def _detect_location_changes(
        self, 
        old_trial: ComprehensiveTrialFields, 
        new_trial: ComprehensiveTrialFields
    ) -> List[Change]:
        """Detect changes in trial locations."""
        changes = []
        
        old_locations = {loc.facility_name: loc for loc in old_trial.locations}
        new_locations = {loc.facility_name: loc for loc in new_trial.locations}
        
        # Check for added locations
        for name, location in new_locations.items():
            if name not in old_locations:
                changes.append(Change(
                    field_name="locations",
                    old_value=None,
                    new_value=location.facility_name,
                    change_type="ADDED",
                    significance="LOW",
                    description=f"New location added: {location.facility_name}"
                ))
        
        # Check for removed locations
        for name, location in old_locations.items():
            if name not in new_locations:
                changes.append(Change(
                    field_name="locations",
                    old_value=location.facility_name,
                    new_value=None,
                    change_type="REMOVED",
                    significance="LOW",
                    description=f"Location removed: {location.facility_name}"
                ))
        
        return changes
    
    def _extract_endpoint_text(self, outcomes: List[Any]) -> str:
        """Extract endpoint text from outcomes list."""
        if not outcomes:
            return ""
        
        parts = []
        for outcome in outcomes:
            if hasattr(outcome, 'measure'):
                measure = outcome.measure or ""
                timeframe = getattr(outcome, 'time_frame', "") or ""
                if measure:
                    if timeframe:
                        parts.append(f"{measure} ({timeframe})")
                    else:
                        parts.append(measure)
        
        return "; ".join(parts)
    
    def _get_field_significance(self, field_name: str) -> str:
        """Get the significance level for a field."""
        if field_name in self.config.high_significance_fields:
            return "HIGH"
        elif field_name in self.config.medium_significance_fields:
            return "MEDIUM"
        elif field_name in self.config.low_significance_fields:
            return "LOW"
        else:
            return "LOW"  # Default to low significance
    
    def has_significant_changes(self, change_summary: TrialChangeSummary) -> bool:
        """Check if there are any significant changes."""
        return change_summary.significant_change_count > 0
    
    def get_change_summary_text(self, change_summary: TrialChangeSummary) -> str:
        """Generate a human-readable summary of changes."""
        if not change_summary.changes:
            return "No changes detected"
        
        summary_parts = [f"Detected {change_summary.change_count} changes:"]
        
        # Group changes by significance
        high_changes = [c for c in change_summary.changes if c.significance == "HIGH"]
        medium_changes = [c for c in change_summary.changes if c.significance == "MEDIUM"]
        low_changes = [c for c in change_summary.changes if c.significance == "LOW"]
        
        if high_changes:
            summary_parts.append(f"\nHIGH significance ({len(high_changes)}):")
            for change in high_changes:
                summary_parts.append(f"  • {change.field_name}: {change.description}")
        
        if medium_changes:
            summary_parts.append(f"\nMEDIUM significance ({len(medium_changes)}):")
            for change in medium_changes:
                summary_parts.append(f"  • {change.field_name}: {change.description}")
        
        if low_changes:
            summary_parts.append(f"\nLOW significance ({len(low_changes)}):")
            for change in low_changes:
                summary_parts.append(f"  • {change.field_name}: {change.description}")
        
        return "\n".join(summary_parts)
