"""
Entity system for canonical data model.

Simplified in-memory entity system for literature retrieval.
No database dependencies - all data structures are in-memory.
"""

from .schema import EntityPack, CompanyInfo, AssetInfo, MechanismInfo, IndicationInfo, RegistryInfo, PublisherInfo, DateRangeInfo

__all__ = [
    "EntityPack",
    "CompanyInfo", 
    "AssetInfo",
    "MechanismInfo",
    "IndicationInfo",
    "RegistryInfo",
    "PublisherInfo",
    "DateRangeInfo"
]
