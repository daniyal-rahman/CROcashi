# Heuristics & Promotion Fixes Implementation

## Overview

This document details the comprehensive fixes implemented for the linking heuristics and promotion system to address the issues identified in the code review:

1. **HP-2 claimed as "complete" but unimplemented** - Fixed status and documentation
2. **Uncalibrated confidence numbers** - Added precision validation gates
3. **Auto-promotion enabled by default** - Added feature flags and precision requirements
4. **Missing link_audit fields** - Added label, label_source, reviewed_by, reviewed_at

## 🔧 Fixes Implemented

### 1. HP-2 Implementation Status - FIXED

**Before**: HP-2 was claimed as "complete" in demo scripts but actually unimplemented
```python
# Demo claimed confidence 0.95 but code showed:
def _apply_hp2_exact_intervention_match(self, doc: Document, 
                                      asset_entities: List[DocumentEntity]) -> List[LinkCandidate]:
    """
    Apply HP-2: Exact intervention name match.
    
    Status: NOT IMPLEMENTED - Requires CT.gov cache integration
    """
    # This heuristic requires CT.gov trial data integration
    # Currently not implemented due to missing trial metadata cache
    # TODO: Implement when CT.gov cache is available
    logger.debug("HP-2: Exact intervention match not implemented - requires CT.gov cache")
    
    return candidates
```

**After**: Clear status and configuration control
```python
# In config/config.yaml
heuristics:
  hp2_exact_intervention_match:
    enabled: false           # Disabled - not implemented
    confidence: 0.95        # Placeholder - not used
    description: "Asset alias matches trial intervention name (requires CT.gov cache)"

# In demo script
print("   HP-2 (Exact intervention match): 0.95 - ❌ NOT IMPLEMENTED - Requires CT.gov cache")
```

**Benefits**:
- ✅ No more false claims about implementation status
- ✅ Clear documentation of what's actually working
- ✅ Configuration-driven enable/disable
- ✅ Proper TODO tracking for future implementation

### 2. Uncalibrated Confidence Numbers - GATED

**Before**: Hardcoded confidence scores used without validation
```python
# Uncalibrated confidence scores used directly
confidence = 0.90  # HP-3: Company PR bias
confidence = 0.85  # HP-4: Abstract specificity
```

**After**: Confidence scores gated behind precision validation
```python
# Configuration with clear warnings
confidence_thresholds:
  auto_promote: 0.95        # Only used when auto_promote_enabled = true
  high_confidence: 0.85     # For review prioritization
  review_required: 0.70     # Below this needs human review

# Heuristic-specific settings with warnings
heuristics:
  hp3_company_pr_bias:
    enabled: true
    confidence: 0.90        # Uncalibrated - needs validation
    description: "Company-hosted PR with code + INN, no ambiguity"
  
  hp4_abstract_specificity:
    enabled: true
    confidence: 0.85        # Uncalibrated - needs validation
    description: "Abstract title has asset + body has phase/indication"
```

**Benefits**:
- ✅ Clear labeling of uncalibrated scores
- ✅ Confidence scores not used for auto-promotion until validated
- ✅ Configuration-driven thresholds
- ✅ Easy to update when calibration data is available

### 3. Auto-Promotion Feature Flag - IMPLEMENTED

**Before**: Auto-promotion enabled by default with uncalibrated confidence
```python
# Auto-promotion happened automatically
def promote_high_confidence_links(self) -> Dict[str, int]:
    # Get high-confidence links
    high_conf_links = self.db_session.query(DocumentLink).filter(
        DocumentLink.confidence >= self.confidence_threshold
    ).all()
    
    # Promote automatically without validation
    for link in high_conf_links:
        if self._should_promote_link(link):
            self._promote_link(link)
```

**After**: Auto-promotion gated behind feature flags and precision validation
```python
# Configuration-driven feature flags
linking_heuristics:
  auto_promote_enabled: false  # Disabled until precision validation
  min_labeled_precision: 0.95  # Minimum 95% precision required
  min_labeled_links: 50        # Minimum 50 labeled links required

# Promotion logic with validation
def promote_high_confidence_links(self) -> Dict[str, int]:
    if not self.auto_promote_enabled:
        logger.info("Auto-promotion disabled - all links kept for review")
        return {
            'study_assets_xref': 0,
            'trial_assets_xref': 0,
            'kept_for_review': 0,
            'reason': 'auto_promotion_disabled'
        }
    
    # Only proceed if feature flag is enabled
    # ... rest of promotion logic
```

**Benefits**:
- ✅ Auto-promotion disabled by default
- ✅ Clear requirements for enabling (95% precision, 50+ links)
- ✅ Feature flag control for different environments
- ✅ All links go to human review until validation complete

### 4. Link Audit Table Enhancement - COMPLETED

**Before**: Missing fields for precision validation
```python
class LinkAudit(Base):
    __tablename__ = "link_audit"
    
    # Missing fields for human review and precision calculation
    # No way to track correct/incorrect predictions
    # No way to calculate precision per heuristic
```

**After**: Complete audit trail with precision validation fields
```python
class LinkAudit(Base):
    __tablename__ = "link_audit"
    
    # Human review fields
    label: Mapped[Optional[bool]] = mapped_column(Boolean)  # True=correct, False=incorrect, NULL=unreviewed
    label_source: Mapped[Optional[str]] = mapped_column(Text)  # "human_review", "gold_standard", "external_validation"
    reviewed_by: Mapped[Optional[str]] = mapped_column(Text)  # Username or system identifier
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # When review was completed
    
    # Indexes for efficient querying
    __table_args__ = (
        # ... existing indexes ...
        Index("ix_link_audit_label", "label"),
        Index("ix_link_audit_reviewed_at", "reviewed_at"),
    )
```

**Benefits**:
- ✅ Complete audit trail for all linking decisions
- ✅ Precision calculation per heuristic
- ✅ Human review tracking
- ✅ Efficient querying for validation

## 🏗️ New Architecture

### Configuration-Driven Heuristics

The new system uses configuration files to control behavior:

```yaml
linking_heuristics:
  # Feature flags for auto-promotion
  auto_promote_enabled: false  # Disabled until precision validation
  min_labeled_precision: 0.95  # Minimum 95% precision required
  min_labeled_links: 50        # Minimum 50 labeled links required
  
  # Confidence thresholds (uncalibrated - use with caution)
  confidence_thresholds:
    auto_promote: 0.95        # Only used when auto_promote_enabled = true
    high_confidence: 0.85     # For review prioritization
    review_required: 0.70     # Below this needs human review
  
  # Heuristic-specific settings
  heuristics:
    hp1_nct_near_asset:
      enabled: true
      confidence: 1.00        # Highest confidence
      description: "NCT ID within ±250 chars of asset mention"
    
    hp2_exact_intervention_match:
      enabled: false           # Disabled - not implemented
      confidence: 0.95        # Placeholder - not used
      description: "Asset alias matches trial intervention name (requires CT.gov cache)"
    
    hp3_company_pr_bias:
      enabled: true
      confidence: 0.90        # Uncalibrated - needs validation
      description: "Company-hosted PR with code + INN, no ambiguity"
    
    hp4_abstract_specificity:
      enabled: true
      confidence: 0.85        # Uncalibrated - needs validation
      description: "Abstract title has asset + body has phase/indication"
```

### Precision Validation System

New methods for calculating and validating precision:

```python
def get_heuristic_precision(self, heuristic: str, start_date: Optional[str] = None, 
                           end_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get precision metrics for a specific heuristic."""
    # Query link_audit table for precision calculation
    # Returns precision, reviewed_links, sufficient_data status

def can_auto_promote_heuristic(self, heuristic: str) -> bool:
    """Check if a heuristic can be used for auto-promotion."""
    # Checks:
    # 1. Auto-promotion globally enabled
    # 2. Sufficient labeled data (≥50 links)
    # 3. Precision meets threshold (≥95%)

def get_promotion_status(self) -> Dict[str, Any]:
    """Get current status of auto-promotion system."""
    # Returns status for all heuristics
    # Shows which can auto-promote and which need more data
```

### Database Functions and Views

New database functions for precision calculation:

```sql
-- View for easy precision calculation
CREATE OR REPLACE VIEW heuristic_precision_summary AS
SELECT 
    heuristic_applied,
    COUNT(*) as total_links,
    COUNT(CASE WHEN label = true THEN 1 END) as correct_links,
    COUNT(CASE WHEN label = false THEN 1 END) as incorrect_links,
    COUNT(CASE WHEN label IS NULL THEN 1 END) as unreviewed_links,
    -- Precision calculation
    CASE 
        WHEN COUNT(CASE WHEN label IS NOT NULL THEN 1 END) > 0 
        THEN ROUND(
            COUNT(CASE WHEN label = true THEN 1 END)::numeric / 
            COUNT(CASE WHEN label IS NOT NULL THEN 1 END)::numeric, 
            4
        )
        ELSE NULL 
    END as precision_rate
FROM link_audit 
WHERE heuristic_applied IS NOT NULL
GROUP BY heuristic_applied;

-- Function to check if auto-promotion is allowed
CREATE OR REPLACE FUNCTION can_auto_promote_heuristic(
    p_heuristic TEXT,
    p_min_precision NUMERIC DEFAULT 0.95,
    p_min_links INTEGER DEFAULT 50
) RETURNS BOOLEAN;
```

## 📋 Usage Examples

### Check Promotion Status

```python
from ncfd.mapping.linking_heuristics import LinkPromoter

promoter = LinkPromoter(db_session)
status = promoter.get_promotion_status()

print(f"Auto-promotion enabled: {status['auto_promote_enabled']}")
for heuristic, data in status['heuristic_status'].items():
    print(f"{heuristic}: precision={data['precision']}, "
          f"reviewed={data['reviewed_links']}, "
          f"can_auto_promote={data['can_auto_promote']}")
```

### Get Heuristic Precision

```python
from ncfd.mapping.linking_heuristics import LinkingHeuristics

heuristics = LinkingHeuristics(db_session)
precision_data = heuristics.get_heuristic_precision('HP-1')

if precision_data and precision_data['sufficient_data']:
    print(f"HP-1 precision: {precision_data['precision']:.3f}")
    print(f"Reviewed links: {precision_data['reviewed_links']}")
else:
    print("Need more labeled data for HP-1")
```

### Enable Auto-Promotion

```python
# In config/config.yaml, change:
linking_heuristics:
  auto_promote_enabled: true  # Only after validation complete
  
# The system will automatically check:
# 1. Each heuristic has ≥50 labeled links
# 2. Each heuristic shows ≥95% precision
# 3. All requirements are met before allowing promotion
```

## 🧪 Testing

### Run the Updated Demo

```bash
cd ncfd
python scripts/demo_linking_heuristics.py
```

Expected output:
```
📋 SUMMARY OF IMPLEMENTATION STATUS
============================================================
✅ COMPLETED:
   - HP-1: NCT near asset (confidence 1.00)
   - HP-3: Company PR bias (confidence 0.90)
   - HP-4: Abstract specificity (confidence 0.85)
   - Link audit table with label fields
   - Precision validation functions
   - Feature flag system
   - Configuration-driven thresholds

❌ NOT IMPLEMENTED:
   - HP-2: Exact intervention match (requires CT.gov cache)
   - Auto-promotion (disabled until precision validation)

🔄 NEXT STEPS:
   1. Collect labeled data for precision validation
   2. Implement HP-2 when CT.gov cache is available
   3. Enable auto-promotion when precision ≥95%
   4. Monitor and calibrate confidence scores
```

### Database Migration

```bash
# Apply the new migration
psql -d ncfd -f migrations/20250123_add_link_audit_fields.sql

# Verify the new fields exist
psql -d ncfd -c "\d link_audit"
```

## 🔄 Migration Guide

### 1. Update Configuration

```bash
# The new config is already in place, but verify:
grep -A 20 "linking_heuristics:" config/config.yaml
```

### 2. Apply Database Migration

```bash
# Run the migration to add new fields
psql -d ncfd -f migrations/20250123_add_link_audit_fields.sql
```

### 3. Update Environment Variables

```bash
# No new environment variables needed
# All configuration is in config files
```

### 4. Verify Implementation

```bash
# Run the demo to see current status
python scripts/demo_linking_heuristics.py

# Check database functions
psql -d ncfd -c "SELECT * FROM heuristic_precision_summary;"
```

## 🎯 Benefits Summary

1. **Accuracy**: No more false claims about implementation status
2. **Safety**: Auto-promotion disabled until precision validation
3. **Transparency**: Clear labeling of uncalibrated confidence scores
4. **Flexibility**: Configuration-driven behavior for different environments
5. **Validation**: Complete audit trail with precision tracking
6. **Monitoring**: Easy to track progress toward auto-promotion enablement

## 🚀 Next Steps

1. **Data Collection**: Start collecting labeled data for precision validation
2. **HP-2 Implementation**: Implement when CT.gov cache is available
3. **Precision Monitoring**: Track precision rates for each heuristic
4. **Auto-Promotion Enablement**: Enable when all requirements are met
5. **Confidence Calibration**: Calibrate confidence scores based on validation data

## 📚 Related Documentation

- [Configuration](../config/config.yaml)
- [Database Models](../src/ncfd/db/models.py)
- [Linking Heuristics](../src/ncfd/mapping/linking_heuristics.py)
- [Database Migration](../migrations/20250123_add_link_audit_fields.sql)
- [Demo Script](../scripts/demo_linking_heuristics.py)
