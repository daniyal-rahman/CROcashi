"""
Phase Normalizer - For Incoming Data Only

Normalizes phase data from external sources (LLMs, user input, etc.) to CT.gov format.
Internal data flow should already be normalized - this normalizer is only for incoming data.
"""

from typing import Optional, Set


class PhaseNormalizer:
    """Normalizes phase data from external sources to CT.gov format."""
    
    # Mapping from various external formats to canonical CT.gov format
    EXTERNAL_TO_CTGOV = {
        # Database format -> CT.gov format
        "P1": "PHASE1",
        "P2": "PHASE2", 
        "P2B": "PHASE2",
        "P2_3": "PHASE2_PHASE3",
        "P3": "PHASE3",
        "P4": "PHASE4",
        
        # Numeric format -> CT.gov format
        "1": "PHASE1",
        "2": "PHASE2",
        "3": "PHASE3",
        "4": "PHASE4",
        
        # Roman numerals -> CT.gov format
        "I": "PHASE1",
        "II": "PHASE2",
        "III": "PHASE3",
        "IV": "PHASE4",
        
        # Descriptive formats -> CT.gov format
        "pivotal": "PHASE3",
        "PIVOTAL": "PHASE3",
        "early": "EARLY_PHASE1",
        "phase1": "PHASE1",
        "phase2": "PHASE2",
        "phase3": "PHASE3",
        "phase4": "PHASE4",
        
        # CT.gov format (already normalized - pass through)
        "PHASE1": "PHASE1",
        "PHASE2": "PHASE2",
        "PHASE3": "PHASE3",
        "PHASE4": "PHASE4",
        "PHASE2_PHASE3": "PHASE2_PHASE3",
        "PHASE1_PHASE2": "PHASE1_PHASE2",
        "PHASE3_PHASE4": "PHASE3_PHASE4",
        "EARLY_PHASE1": "EARLY_PHASE1",
    }
    
    # Valid CT.gov phase values
    VALID_PHASES: Set[str] = {
        "PHASE1", "PHASE2", "PHASE3", "PHASE4",
        "PHASE2_PHASE3", "PHASE1_PHASE2", "PHASE3_PHASE4",
        "EARLY_PHASE1"
    }
    
    @classmethod
    def normalize(cls, phase: Optional[str]) -> str:
        """
        Normalize external phase data to CT.gov format.
        
        Args:
            phase: External phase data (from LLMs, user input, etc.)
            
        Returns:
            Normalized phase in CT.gov format, or "UNKNOWN" if unrecognized
        """
        if not phase:
            return "UNKNOWN"
        
        # Normalize to uppercase for lookup
        phase_upper = phase.strip().upper()
        
        # Direct lookup
        normalized = cls.EXTERNAL_TO_CTGOV.get(phase_upper)
        if normalized:
            return normalized
        
        # Handle compound phases like "2/3" -> "PHASE2_PHASE3"
        if "/" in phase_upper:
            parts = phase_upper.split("/")
            if len(parts) == 2:
                part1 = cls.EXTERNAL_TO_CTGOV.get(parts[0].strip())
                part2 = cls.EXTERNAL_TO_CTGOV.get(parts[1].strip())
                if part1 and part2:
                    # Create compound phase
                    if part1 == "PHASE2" and part2 == "PHASE3":
                        return "PHASE2_PHASE3"
                    elif part1 == "PHASE1" and part2 == "PHASE2":
                        return "PHASE1_PHASE2"
                    elif part1 == "PHASE3" and part2 == "PHASE4":
                        return "PHASE3_PHASE4"
        
        return "UNKNOWN"
    
    @classmethod
    def is_valid_phase(cls, phase: str) -> bool:
        """
        Check if phase is a valid CT.gov phase.
        
        Args:
            phase: Phase to validate
            
        Returns:
            True if valid CT.gov phase
        """
        return phase in cls.VALID_PHASES
    
    @classmethod
    def is_phase_2_or_3(cls, phase: str) -> bool:
        """
        Check if phase is Phase 2 or 3 (for filtering).
        
        Args:
            phase: Phase to check
            
        Returns:
            True if Phase 2 or 3
        """
        return phase in {"PHASE2", "PHASE3", "PHASE2_PHASE3"}
    
    @classmethod
    def get_phase_display_name(cls, phase: str) -> str:
        """
        Get human-readable display name for phase.
        
        Args:
            phase: CT.gov phase format
            
        Returns:
            Human-readable phase name
        """
        display_names = {
            "PHASE1": "Phase 1",
            "PHASE2": "Phase 2",
            "PHASE3": "Phase 3",
            "PHASE4": "Phase 4",
            "PHASE2_PHASE3": "Phase 2/3",
            "PHASE1_PHASE2": "Phase 1/2",
            "PHASE3_PHASE4": "Phase 3/4",
            "EARLY_PHASE1": "Early Phase 1",
        }
        return display_names.get(phase, phase)
