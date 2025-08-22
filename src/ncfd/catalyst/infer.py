"""Catalyst window inference engine for Phase 10."""

from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Iterable, List, Tuple
from math import exp

from .models import StudyHint, CatalystWindow, SlipStats


# ---------------------------- Constants ----------------------------

_QMAP = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
_HALF_MAP = {1: (1, 6), 2: (7, 12)}
_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", 
     "July", "August", "September", "October", "November", "December"], start=1)}

# Regex patterns for parsing different date formats
MONTH_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(\d{4})\b", re.I)
QUARTER_RE = re.compile(r"\bQ([1-4])\s*(20\d{2})\b", re.I)
HALF_RE = re.compile(r"\bH([12])\s*(20\d{2})\b", re.I)
YEAR_RE = re.compile(r"\b(20\d{2})\b")
CONFERENCE_RE = re.compile(r"\b(ESMO|ASCO|ASH|AACR|ASCO-GI|ASCO-BC|ESMO-IO)\s+(20\d{2})\b", re.I)


# ---------------------------- Parsing helpers ----------------------------

def parse_exact_date(text: str) -> Tuple[date, date, float]:
    """Parse exact date from text (e.g., 'topline on Nov 3, 2025')."""
    match = MONTH_RE.search(text)
    if match:
        month_name, day, year = match.groups()
        month = _MONTHS[month_name.lower()]
        parsed_date = date(int(year), month, int(day))
        # Window: [date - 1d, date + 2d]
        start = parsed_date - timedelta(days=1)
        end = parsed_date + timedelta(days=2)
        return start, end, 0.95  # High weight for exact dates
    return None, None, 0.0


def parse_quarter(text: str) -> Tuple[date, date, float]:
    """Parse quarter from text (e.g., 'Q1 2025')."""
    match = QUARTER_RE.search(text)
    if match:
        quarter, year = match.groups()
        quarter = int(quarter)
        year = int(year)
        start_month, end_month = _QMAP[quarter]
        start = date(year, start_month, 1)
        if quarter == 4:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, end_month + 1, 1) - timedelta(days=1)
        return start, end, 0.6
    return None, None, 0.0


def parse_half(text: str) -> Tuple[date, date, float]:
    """Parse half-year from text (e.g., 'H1 2025')."""
    match = HALF_RE.search(text)
    if match:
        half, year = match.groups()
        half = int(half)
        year = int(year)
        start_month, end_month = _HALF_MAP[half]
        start = date(year, start_month, 1)
        if half == 2:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, end_month + 1, 1) - timedelta(days=1)
        return start, end, 0.6
    return None, None, 0.0


def parse_year(text: str) -> Tuple[date, date, float]:
    """Parse year from text (e.g., 'by end of 2025')."""
    match = YEAR_RE.search(text)
    if match:
        year = int(match.group(1))
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        return start, end, 0.6
    return None, None, 0.0


def parse_conference(text: str) -> Tuple[date, date, float]:
    """Parse conference from text (e.g., 'results at ESMO 2025')."""
    match = CONFERENCE_RE.search(text)
    if match:
        conf_name, year = match.groups()
        year = int(year)
        # Conference dates (simplified - in practice would use actual conference dates)
        if conf_name.upper() == "ESMO":
            start = date(year, 9, 15)  # September
            end = date(year, 9, 20)
        elif conf_name.upper() == "ASCO":
            start = date(year, 6, 1)   # June
            end = date(year, 6, 5)
        elif conf_name.upper() == "ASH":
            start = date(year, 12, 5)  # December
            end = date(year, 12, 9)
        else:
            # Generic conference
            start = date(year, 6, 1)
            end = date(year, 6, 5)
        
        # Window: [conf_start - 2d (embargo), conf_end + 1d]
        start = start - timedelta(days=2)
        end = end + timedelta(days=1)
        return start, end, 0.8
    return None, None, 0.0


def parse_study_hints(extracted_jsonb: dict, study_id: int, url: str = None) -> List[StudyHint]:
    """Parse study hints from extracted JSONB data."""
    hints = []
    
    # Check for explicit readout dates
    if 'readout' in extracted_jsonb:
        readout = extracted_jsonb['readout']
        
        # Exact date
        if 'expected_date' in readout:
            try:
                expected_date = date.fromisoformat(readout['expected_date'])
                start = expected_date - timedelta(days=1)
                end = expected_date + timedelta(days=2)
                hints.append(StudyHint(
                    kind="exact_date",
                    start=start,
                    end=end,
                    weight=0.95,
                    raw_text=f"Expected date: {readout['expected_date']}",
                    study_id=study_id,
                    url=url
                ))
            except ValueError:
                pass
        
        # Conference
        if 'conference' in readout:
            conf = readout['conference']
            if 'name' in conf and 'year' in conf:
                conf_text = f"results at {conf['name']} {conf['year']}"
                start, end, weight = parse_conference(conf_text)
                if start and end:
                    hints.append(StudyHint(
                        kind="conference",
                        start=start,
                        end=end,
                        weight=weight,
                        raw_text=conf_text,
                        study_id=study_id,
                        url=url
                    ))
        
        # Bucket-based dates
        if 'bucket' in readout:
            bucket = readout['bucket']
            if bucket == 'month' and 'month' in readout:
                # Parse month
                pass  # TODO: implement month parsing
            elif bucket == 'quarter' and 'quarter' in readout:
                # Parse quarter
                pass  # TODO: implement quarter parsing
            elif bucket == 'half' and 'half' in readout:
                # Parse half
                pass  # TODO: implement half parsing
            elif bucket == 'year' and 'year' in readout:
                # Parse year
                pass  # TODO: implement year parsing
    
    # Check quoted text for additional hints
    if 'quoted_text' in extracted_jsonb:
        quoted_text = extracted_jsonb['quoted_text']
        
        # Try to parse different date formats
        for parser in [parse_exact_date, parse_quarter, parse_half, parse_year, parse_conference]:
            start, end, weight = parser(quoted_text)
            if start and end:
                hints.append(StudyHint(
                    kind="freeform",
                    start=start,
                    end=end,
                    weight=weight,
                    raw_text=quoted_text,
                    study_id=study_id,
                    url=url
                ))
                break  # Use first successful parse
    
    return hints


# ---------------------------- Core logic ----------------------------

def _apply_slip(start: date, end: date, slip: SlipStats) -> Tuple[date, date]:
    """Apply slip factors to a date window."""
    # Shift: clamp mean_slip_days between -30 and +75
    shift = max(-30, min(75, slip.mean_slip_days))
    
    # Widen: based on p90-p10 spread, capped at 45 days
    widen_days = max(0, (slip.p90_days - slip.p10_days) // 2)
    widen_pad = min(14, widen_days)
    
    new_start = start + timedelta(days=shift - widen_pad)
    new_end = end + timedelta(days=shift + widen_pad)
    
    return new_start, new_end


def _w_recency(weight: float, hint_age_days: int) -> float:
    """Apply recency boost to hint weight."""
    # Exponential decay over 180 days
    recency_factor = min(1.0, 0.5 + 0.5 * exp(-hint_age_days / 180))
    return weight * recency_factor


def _fuse_windows(windows: List[Tuple[date, date, float, StudyHint]]) -> CatalystWindow:
    """Fuse multiple candidate windows into a single window."""
    if not windows:
        raise ValueError("No windows to fuse")
    
    # Sort by weight (descending)
    windows = sorted(windows, key=lambda w: w[2], reverse=True)
    
    if len(windows) == 1:
        start, end, weight, hint = windows[0]
        span = (end - start).days
        certainty = max(0.0, min(1.0, 1 - (span / 30) * (1 - weight)))
        return CatalystWindow(
            trial_id=hint.study_id,  # This should be trial_id, not study_id
            window_start=start,
            window_end=end,
            certainty=certainty,
            sources=[hint]
        )
    
    # Get top 2 windows
    s1, e1, w1, h1 = windows[0]
    s2, e2, w2, h2 = windows[1]
    
    # Try intersection first
    inter_start = max(s1, s2)
    inter_end = min(e1, e2)
    
    if inter_start <= inter_end:
        # Windows overlap - use intersection
        span = (inter_end - inter_start).days
        best_weight = max(w1, w2)
        certainty = max(0.0, min(1.0, 1 - (span / 30) * (1 - best_weight)))
        return CatalystWindow(
            trial_id=h1.study_id,  # This should be trial_id, not study_id
            window_start=inter_start,
            window_end=inter_end,
            certainty=certainty,
            sources=[h1, h2]
        )
    else:
        # No overlap - use weighted union preferring shorter span
        union_start = min(s1, s2)
        union_end = max(e1, e2)
        span = (union_end - union_start).days
        best_weight = max(w1, w2)
        certainty = max(0.0, min(1.0, 1 - (span / 45) * (1 - best_weight)))
        return CatalystWindow(
            trial_id=h1.study_id,  # This should be trial_id, not study_id
            window_start=union_start,
            window_end=union_end,
            certainty=certainty,
            sources=[h1, h2]
        )


def infer_catalyst_window(
    trial_id: int,
    epcd: date,
    epcd_version_age_days: int,
    study_hints: List[StudyHint],
    slip_stats: SlipStats,
    trial_status: str = None,
    existing_label: dict = None
) -> CatalystWindow:
    """
    Infer catalyst window for a trial.
    
    Args:
        trial_id: Trial ID
        epcd: Estimated primary completion date
        epcd_version_age_days: Age of EPCD version in days
        study_hints: List of study hints from PRs/abstracts
        slip_stats: Sponsor-specific slip statistics
        trial_status: Current trial status
        existing_label: Existing label if trial completed/terminated
    
    Returns:
        CatalystWindow with inferred start/end dates and certainty
    """
    
    # If trial is completed/terminated and has a label, use exact date
    if trial_status in ['Completed', 'Terminated'] and existing_label:
        event_date = existing_label.get('event_date')
        if event_date:
            return CatalystWindow(
                trial_id=trial_id,
                window_start=event_date,
                window_end=event_date,
                certainty=1.0,
                sources=[],
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
    
    # Base anchor: EPCD with ±14/+28 day window
    base_start = epcd - timedelta(days=14)
    base_end = epcd + timedelta(days=28)
    base_start, base_end = _apply_slip(base_start, base_end, slip_stats)
    w_epcd = _w_recency(0.4, epcd_version_age_days)
    
    # Create base hint
    base_hint = StudyHint(
        kind="freeform",
        start=base_start,
        end=base_end,
        weight=w_epcd,
        raw_text="EPCD base",
        study_id=0  # Placeholder
    )
    
    # Collect all candidate windows
    candidates = [(base_start, base_end, w_epcd, base_hint)]
    
    # Add windows from study hints
    for hint in study_hints:
        start, end = _apply_slip(hint.start, hint.end, slip_stats)
        # Calculate hint age (simplified - in practice would use actual hint date)
        hint_age_days = 30  # Placeholder
        adjusted_weight = _w_recency(hint.weight, hint_age_days)
        candidates.append((start, end, adjusted_weight, hint))
    
    # Fuse windows and return result
    result = _fuse_windows(candidates)
    result.trial_id = trial_id  # Fix the trial_id
    return result
