"""
Trial version tracking for failure detection system.

This module provides comprehensive trial version tracking, change detection,
and material change identification for monitoring trial protocol evolution.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
import hashlib

from ..db.models import Trial, TrialVersion, Study
from ..db.session import get_session
from ..signals import S1_endpoint_changed


@dataclass
class ChangeDetectionResult:
    """Result of change detection analysis."""
    has_changes: bool
    material_changes: bool
    change_summary: List[str]
    change_score: float
    detected_at: datetime
    previous_version: Optional[str] = None
    current_version: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MaterialChange:
    """Represents a material change in trial protocol."""
    change_type: str
    field_path: str
    old_value: Any
    new_value: Any
    severity: str  # "H", "M", "L"
    description: str
    detected_at: datetime
    impact_assessment: Optional[str] = None


@dataclass
class TrialChangeSummary:
    """Summary of changes across trial versions."""
    trial_id: str
    total_versions: int
    change_frequency: float
    material_changes_count: int
    last_change_date: Optional[datetime]
    change_timeline: List[Dict[str, Any]]
    risk_assessment: str  # "H", "M", "L"
    metadata: Optional[Dict[str, Any]] = None


class TrialVersionTracker:
    """Comprehensive trial version tracking and change detection."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the trial version tracker.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.material_change_threshold = self.config.get("material_change_threshold", 0.3)
        self.change_detection_sensitivity = self.config.get("change_detection_sensitivity", "medium")
        self.max_versions_to_compare = self.config.get("max_versions_to_compare", 5)
        self.change_score_weights = self.config.get("change_score_weights", {
            "endpoint": 1.0,
            "sample_size": 0.8,
            "analysis_plan": 0.9,
            "inclusion_criteria": 0.7,
            "primary_outcome": 1.0,
            "statistical_methods": 0.8
        })
    
    def track_trial_changes(self, 
                           trial_id: str,
                           new_study_card: Dict[str, Any],
                           run_id: Optional[str] = None) -> ChangeDetectionResult:
        """
        Track changes for a trial and detect material modifications.
        
        Args:
            trial_id: Trial identifier
            new_study_card: New study card data
            run_id: Run identifier for tracking
            
        Returns:
            ChangeDetectionResult with change analysis
        """
        try:
            with get_session() as session:
                # Get trial and existing versions
                trial = session.query(Trial).filter_by(trial_id=trial_id).first()
                if not trial:
                    raise ValueError(f"Trial {trial_id} not found")
                
                existing_versions = session.query(TrialVersion).filter_by(
                    trial_id=trial_id
                ).order_by(TrialVersion.captured_at.desc()).limit(self.max_versions_to_compare).all()
                
                if not existing_versions:
                    # First version, no changes to detect
                    return ChangeDetectionResult(
                        has_changes=False,
                        material_changes=False,
                        change_summary=[],
                        change_score=0.0,
                        detected_at=datetime.now(),
                        metadata={"status": "first_version"}
                    )
                
                # Compare with most recent version
                latest_version = existing_versions[0]
                changes = self._detect_changes(latest_version.raw_jsonb, new_study_card)
                
                # Determine if changes are material
                material_changes = self._assess_material_changes(changes)
                change_score = self._calculate_change_score(changes)
                
                # Generate change summary
                change_summary = self._generate_change_summary(changes)
                
                # Create new trial version
                new_version = TrialVersion(
                    trial_id=trial_id,
                    captured_at=datetime.now(),
                    raw_jsonb=new_study_card,
                    primary_endpoint_text=new_study_card.get("primary_endpoint_text", ""),
                    sample_size=new_study_card.get("sample_size"),
                    analysis_plan_text=new_study_card.get("analysis_plan_text", ""),
                    changes_jsonb={
                        "change_detection_result": asdict(ChangeDetectionResult(
                            has_changes=len(changes) > 0,
                            material_changes=material_changes,
                            change_summary=change_summary,
                            change_score=change_score,
                            detected_at=datetime.now(),
                            previous_version=latest_version.version_id,
                            current_version=None,  # Will be set after commit
                            metadata={
                                "run_id": run_id,
                                "changes_detected": len(changes),
                                "material_changes_count": sum(1 for c in changes if c.get("material", False))
                            }
                        )),
                        "detailed_changes": changes
                    },
                    metadata={
                        "change_tracking": True,
                        "run_id": run_id,
                        "change_score": change_score,
                        "material_changes": material_changes
                    }
                )
                
                session.add(new_version)
                session.commit()
                
                # Update change detection result with current version ID
                new_version.changes_jsonb["change_detection_result"]["current_version"] = new_version.version_id
                session.commit()
                
                self.logger.info(f"Tracked changes for trial {trial_id}: {len(changes)} changes, "
                               f"material: {material_changes}, score: {change_score:.3f}")
                
                return ChangeDetectionResult(
                    has_changes=len(changes) > 0,
                    material_changes=material_changes,
                    change_summary=change_summary,
                    change_score=change_score,
                    detected_at=datetime.now(),
                    previous_version=latest_version.version_id,
                    current_version=new_version.version_id,
                    metadata={
                        "run_id": run_id,
                        "changes_detected": len(changes),
                        "material_changes_count": sum(1 for c in changes if c.get("material", False))
                    }
                )
                
        except Exception as e:
            self.logger.error(f"Change tracking failed for trial {trial_id}: {e}")
            raise
    
    def detect_material_changes(self, 
                               trial_id: str,
                               version_id: Optional[str] = None) -> List[MaterialChange]:
        """
        Detect material changes in a specific trial version.
        
        Args:
            trial_id: Trial identifier
            version_id: Specific version to analyze (optional)
            
        Returns:
            List of material changes detected
        """
        try:
            with get_session() as session:
                # Get trial versions
                query = session.query(TrialVersion).filter_by(trial_id=trial_id)
                if version_id:
                    query = query.filter_by(version_id=version_id)
                
                versions = query.order_by(TrialVersion.captured_at.desc()).limit(2).all()
                
                if len(versions) < 2:
                    return []  # Need at least 2 versions to detect changes
                
                current_version = versions[0]
                previous_version = versions[1]
                
                # Detect changes
                changes = self._detect_changes(
                    previous_version.raw_jsonb,
                    current_version.raw_jsonb
                )
                
                # Filter for material changes
                material_changes = []
                for change in changes:
                    if change.get("material", False):
                        material_change = MaterialChange(
                            change_type=change.get("type", "unknown"),
                            field_path=change.get("path", ""),
                            old_value=change.get("old_value"),
                            new_value=change.get("new_value"),
                            severity=change.get("severity", "M"),
                            description=change.get("description", ""),
                            detected_at=current_version.captured_at,
                            impact_assessment=change.get("impact_assessment")
                        )
                        material_changes.append(material_change)
                
                return material_changes
                
        except Exception as e:
            self.logger.error(f"Material change detection failed for trial {trial_id}: {e}")
            return []
    
    def generate_change_summary(self, 
                               trial_id: str,
                               days_back: int = 365) -> TrialChangeSummary:
        """
        Generate comprehensive change summary for a trial.
        
        Args:
            trial_id: Trial identifier
            days_back: Number of days to look back
            
        Returns:
            TrialChangeSummary with comprehensive change analysis
        """
        try:
            with get_session() as session:
                # Get trial versions within time window
                cutoff_date = datetime.now() - timedelta(days=days_back)
                
                versions = session.query(TrialVersion).filter(
                    TrialVersion.trial_id == trial_id,
                    TrialVersion.captured_at >= cutoff_date
                ).order_by(TrialVersion.captured_at.desc()).all()
                
                if not versions:
                    return TrialChangeSummary(
                        trial_id=trial_id,
                        total_versions=0,
                        change_frequency=0.0,
                        material_changes_count=0,
                        last_change_date=None,
                        change_timeline=[],
                        risk_assessment="L",
                        metadata={"status": "no_versions_in_window"}
                    )
                
                # Analyze change timeline
                change_timeline = []
                material_changes_count = 0
                
                for i, version in enumerate(versions):
                    if i == 0:  # Latest version
                        continue
                    
                    # Get changes for this version
                    changes = version.changes_jsonb.get("detailed_changes", [])
                    material_changes = sum(1 for c in changes if c.get("material", False))
                    material_changes_count += material_changes
                    
                    change_timeline.append({
                        "version_id": version.version_id,
                        "captured_at": version.captured_at.isoformat(),
                        "changes_count": len(changes),
                        "material_changes_count": material_changes,
                        "change_score": version.changes_jsonb.get("change_detection_result", {}).get("change_score", 0.0)
                    })
                
                # Calculate metrics
                total_versions = len(versions)
                change_frequency = len(change_timeline) / max(1, (versions[0].captured_at - versions[-1].captured_at).days) * 365
                last_change_date = versions[0].captured_at if len(versions) > 1 else None
                
                # Risk assessment
                if material_changes_count >= 5 or change_frequency > 12:
                    risk_assessment = "H"
                elif material_changes_count >= 2 or change_frequency > 6:
                    risk_assessment = "M"
                else:
                    risk_assessment = "L"
                
                return TrialChangeSummary(
                    trial_id=trial_id,
                    total_versions=total_versions,
                    change_frequency=change_frequency,
                    material_changes_count=material_changes_count,
                    last_change_date=last_change_date,
                    change_timeline=change_timeline,
                    risk_assessment=risk_assessment,
                    metadata={
                        "analysis_window_days": days_back,
                        "cutoff_date": cutoff_date.isoformat()
                    }
                )
                
        except Exception as e:
            self.logger.error(f"Change summary generation failed for trial {trial_id}: {e}")
            return TrialChangeSummary(
                trial_id=trial_id,
                total_versions=0,
                change_frequency=0.0,
                material_changes_count=0,
                last_change_date=None,
                change_timeline=[],
                risk_assessment="L",
                metadata={"error": str(e)}
            )
    
    def _detect_changes(self, 
                        old_data: Dict[str, Any],
                        new_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect changes between two data structures."""
        changes = []
        
        # Compare top-level fields
        all_keys = set(old_data.keys()) | set(new_data.keys())
        
        for key in all_keys:
            old_value = old_data.get(key)
            new_value = new_data.get(key)
            
            if key in old_data and key in new_data:
                # Field exists in both, check for changes
                if self._values_differ(old_value, new_value):
                    change = self._analyze_field_change(key, old_value, new_value)
                    if change:
                        changes.append(change)
            elif key in old_data:
                # Field removed
                changes.append({
                    "type": "removed",
                    "path": key,
                    "old_value": old_value,
                    "new_value": None,
                    "material": self._is_material_change(key, old_value, None),
                    "severity": self._assess_change_severity(key, old_value, None),
                    "description": f"Field '{key}' was removed"
                })
            else:
                # Field added
                changes.append({
                    "type": "added",
                    "path": key,
                    "old_value": None,
                    "new_value": new_value,
                    "material": self._is_material_change(key, None, new_value),
                    "severity": self._assess_change_severity(key, None, new_value),
                    "description": f"Field '{key}' was added"
                })
        
        return changes
    
    def _values_differ(self, old_value: Any, new_value: Any) -> bool:
        """Check if two values are different."""
        if old_value is None and new_value is None:
            return False
        if old_value is None or new_value is None:
            return True
        
        # Handle different types
        if type(old_value) != type(new_value):
            return True
        
        # Handle dictionaries recursively
        if isinstance(old_value, dict):
            if not isinstance(new_value, dict):
                return True
            return self._detect_changes(old_value, new_value) != []
        
        # Handle lists
        if isinstance(old_value, list):
            if not isinstance(new_value, list):
                return True
            if len(old_value) != len(new_value):
                return True
            return any(self._values_differ(ov, nv) for ov, nv in zip(old_value, new_value))
        
        # Handle other types
        return old_value != new_value
    
    def _analyze_field_change(self, 
                             field_path: str,
                             old_value: Any,
                             new_value: Any) -> Optional[Dict[str, Any]]:
        """Analyze a specific field change."""
        if not self._values_differ(old_value, new_value):
            return None
        
        # Special handling for specific fields
        if field_path == "primary_endpoint_text":
            return self._analyze_endpoint_change(old_value, new_value)
        elif field_path == "sample_size":
            return self._analyze_sample_size_change(old_value, new_value)
        elif field_path == "analysis_plan":
            return self._analyze_analysis_plan_change(old_value, new_value)
        elif field_path == "arms":
            return self._analyze_arms_change(old_value, new_value)
        
        # Generic change analysis
        return {
            "type": "modified",
            "path": field_path,
            "old_value": old_value,
            "new_value": new_value,
            "material": self._is_material_change(field_path, old_value, new_value),
            "severity": self._assess_change_severity(field_path, old_value, new_value),
            "description": f"Field '{field_path}' was modified"
        }
    
    def _analyze_endpoint_change(self, old_endpoint: str, new_endpoint: str) -> Dict[str, Any]:
        """Analyze endpoint changes specifically."""
        # Use S1 signal logic to determine if change is material
        similarity = SequenceMatcher(None, old_endpoint or "", new_endpoint or "").ratio()
        
        is_material = similarity < (1 - self.material_change_threshold)
        
        return {
            "type": "endpoint_modified",
            "path": "primary_endpoint_text",
            "old_value": old_endpoint,
            "new_value": new_endpoint,
            "material": is_material,
            "severity": "H" if is_material else "M",
            "description": f"Primary endpoint {'significantly' if is_material else 'slightly'} modified",
            "similarity_score": similarity,
            "impact_assessment": "High impact on trial validity" if is_material else "Low impact"
        }
    
    def _analyze_sample_size_change(self, old_size: int, new_size: int) -> Dict[str, Any]:
        """Analyze sample size changes."""
        if old_size is None or new_size is None:
            return None
        
        change_ratio = abs(new_size - old_size) / old_size
        is_material = change_ratio > 0.2  # 20% change threshold
        
        return {
            "type": "sample_size_modified",
            "path": "sample_size",
            "old_value": old_size,
            "new_value": new_size,
            "material": is_material,
            "severity": "H" if is_material else "M",
            "description": f"Sample size changed from {old_size} to {new_size} ({change_ratio:.1%} change)",
            "change_ratio": change_ratio,
            "impact_assessment": "May affect statistical power" if is_material else "Minor adjustment"
        }
    
    def _analyze_analysis_plan_change(self, old_plan: Dict, new_plan: Dict) -> Dict[str, Any]:
        """Analyze analysis plan changes."""
        if not isinstance(old_plan, dict) or not isinstance(new_plan, dict):
            return None
        
        # Check for critical changes
        critical_fields = ["alpha", "one_sided", "planned_interims"]
        critical_changes = []
        
        for field in critical_fields:
            if field in old_plan and field in new_plan:
                if old_plan[field] != new_plan[field]:
                    critical_changes.append(field)
        
        is_material = len(critical_changes) > 0
        
        return {
            "type": "analysis_plan_modified",
            "path": "analysis_plan",
            "old_value": old_plan,
            "new_value": new_plan,
            "material": is_material,
            "severity": "H" if is_material else "M",
            "description": f"Analysis plan modified with {len(critical_changes)} critical changes",
            "critical_changes": critical_changes,
            "impact_assessment": "May affect statistical validity" if is_material else "Minor adjustments"
        }
    
    def _analyze_arms_change(self, old_arms: Dict, new_arms: Dict) -> Dict[str, Any]:
        """Analyze treatment arms changes."""
        if not isinstance(old_arms, dict) or not isinstance(new_arms, dict):
            return None
        
        # Check for arm structure changes
        old_arm_count = len(old_arms)
        new_arm_count = len(new_arms)
        
        is_material = old_arm_count != new_arm_count
        
        return {
            "type": "arms_modified",
            "path": "arms",
            "old_value": old_arms,
            "new_value": new_arms,
            "material": is_material,
            "severity": "H" if is_material else "M",
            "description": f"Treatment arms changed from {old_arm_count} to {new_arm_count}",
            "arm_count_change": new_arm_count - old_arm_count,
            "impact_assessment": "Major trial design change" if is_material else "Minor arm adjustment"
        }
    
    def _is_material_change(self, field_path: str, old_value: Any, new_value: Any) -> bool:
        """Determine if a change is material."""
        # High-impact fields are always material
        high_impact_fields = [
            "primary_endpoint_text", "sample_size", "analysis_plan", "arms",
            "primary_result", "subgroups", "inclusion_criteria", "exclusion_criteria"
        ]
        
        if field_path in high_impact_fields:
            return True
        
        # Check change magnitude for numeric fields
        if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
            if old_value != 0:
                change_ratio = abs(new_value - old_value) / abs(old_value)
                return change_ratio > self.material_change_threshold
        
        # Check text similarity for string fields
        if isinstance(old_value, str) and isinstance(new_value, str):
            similarity = SequenceMatcher(None, old_value, new_value).ratio()
            return similarity < (1 - self.material_change_threshold)
        
        return False
    
    def _assess_change_severity(self, field_path: str, old_value: Any, new_value: Any) -> str:
        """Assess the severity of a change."""
        if self._is_material_change(field_path, old_value, new_value):
            # High-impact fields get high severity
            high_impact_fields = ["primary_endpoint_text", "sample_size", "analysis_plan"]
            if field_path in high_impact_fields:
                return "H"
            return "M"
        return "L"
    
    def _assess_material_changes(self, changes: List[Dict[str, Any]]) -> bool:
        """Assess if any changes are material."""
        return any(change.get("material", False) for change in changes)
    
    def _calculate_change_score(self, changes: List[Dict[str, Any]]) -> float:
        """Calculate a numerical change score."""
        if not changes:
            return 0.0
        
        total_score = 0.0
        total_weight = 0.0
        
        for change in changes:
            field_path = change.get("path", "")
            severity = change.get("severity", "M")
            
            # Get field weight
            field_weight = 1.0
            for field_pattern, weight in self.change_score_weights.items():
                if field_pattern in field_path:
                    field_weight = weight
                    break
            
            # Get severity weight
            severity_weight = {"H": 1.0, "M": 0.6, "L": 0.3}.get(severity, 0.5)
            
            # Calculate change score
            change_score = field_weight * severity_weight
            total_score += change_score
            total_weight += field_weight
        
        return total_score / max(total_weight, 1.0)
    
    def _generate_change_summary(self, changes: List[Dict[str, Any]]) -> List[str]:
        """Generate human-readable change summary."""
        if not changes:
            return ["No changes detected"]
        
        summary = []
        material_changes = [c for c in changes if c.get("material", False)]
        
        if material_changes:
            summary.append(f"{len(material_changes)} material changes detected")
            for change in material_changes[:3]:  # Show first 3 material changes
                summary.append(f"  • {change.get('description', 'Change detected')}")
        else:
            summary.append(f"{len(changes)} minor changes detected")
        
        # Add change types
        change_types = {}
        for change in changes:
            change_type = change.get("type", "unknown")
            change_types[change_type] = change_types.get(change_type, 0) + 1
        
        for change_type, count in change_types.items():
            summary.append(f"  • {count} {change_type} changes")
        
        return summary


# Convenience functions
def track_trial_changes(trial_id: str,
                       new_study_card: Dict[str, Any],
                       run_id: Optional[str] = None) -> ChangeDetectionResult:
    """Track changes for a trial."""
    tracker = TrialVersionTracker()
    return tracker.track_trial_changes(trial_id, new_study_card, run_id)


def detect_material_changes(trial_id: str,
                           version_id: Optional[str] = None) -> List[MaterialChange]:
    """Detect material changes in a trial."""
    tracker = TrialVersionTracker()
    return tracker.detect_material_changes(trial_id, version_id)


def generate_change_summary(trial_id: str,
                           days_back: int = 365) -> TrialChangeSummary:
    """Generate change summary for a trial."""
    tracker = TrialVersionTracker()
    return tracker.generate_change_summary(trial_id, days_back)
