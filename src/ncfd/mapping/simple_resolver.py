"""
Simplified Three-Tier Resolver System

This module provides a clean, simple resolver that implements:
1. Exact Match (deterministic)
2. Fuzzy Match (Jaro-Winkler similarity)
3. LLM Match (with web search for aliases/subsidiaries)

The LLM tier serves as a learning system that discovers new company relationships
and feeds them back into the database for better future matching.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.models import Company, CompanyAlias, SponsorResolution, ManualReviewQueue, AcademicBlacklist, LLMDiscovery
from .normalize import norm_name, has_academic_keywords
from .deterministic import resolve_company as det_resolve, Resolution

logger = logging.getLogger(__name__)


@dataclass
class ResolutionOutput:
    """Result of sponsor resolution."""
    company_id: Optional[int]
    match_method: str  # exact, fuzzy, llm, manual, academic_skip
    confidence: float
    evidence: Dict[str, Any]
    aliases_discovered: List[str] = None


class SimpleResolver:
    """
    Simplified three-tier resolver system.
    
    Flow: Academic Check → Exact Match → Fuzzy Match → LLM Match → Manual Review
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.logger = logging.getLogger(__name__)
    
    def resolve_sponsor(self, nct_id: str, sponsor_text: str) -> ResolutionOutput:
        """
        Resolve sponsor text to company using three-tier approach.
        
        Args:
            nct_id: Clinical trial NCT ID
            sponsor_text: Raw sponsor text from trial
            
        Returns:
            ResolutionOutput with company match or manual review flag
        """
        if not sponsor_text or not sponsor_text.strip():
            return ResolutionOutput(
                company_id=None,
                match_method="manual",
                confidence=0.0,
                evidence={"reason": "empty_sponsor_text"}
            )
        
        # Step 1: Check academic blacklist
        if self._is_academic_sponsor(sponsor_text):
            self.logger.info(f"NCT {nct_id}: Academic sponsor detected: {sponsor_text}")
            return ResolutionOutput(
                company_id=None,
                match_method="academic_skip",
                confidence=0.95,
                evidence={"reason": "academic_sponsor", "sponsor": sponsor_text}
            )
        
        # Step 2: Try exact match (deterministic)
        exact_result = det_resolve(self.session, sponsor_text)
        if exact_result:
            self.logger.info(f"NCT {nct_id}: Exact match found: {exact_result.company_id}")
            self._save_resolution(nct_id, sponsor_text, exact_result.company_id, "exact", 1.0, exact_result.evidence)
            return ResolutionOutput(
                company_id=exact_result.company_id,
                match_method="exact",
                confidence=1.0,
                evidence=exact_result.evidence
            )
        
        # Step 3: Try fuzzy match
        fuzzy_result = self._fuzzy_match(sponsor_text)
        if fuzzy_result:
            self.logger.info(f"NCT {nct_id}: Fuzzy match found: {fuzzy_result.company_id}")
            self._save_resolution(nct_id, sponsor_text, fuzzy_result.company_id, "fuzzy", fuzzy_result.confidence, fuzzy_result.evidence)
            return ResolutionOutput(
                company_id=fuzzy_result.company_id,
                match_method="fuzzy",
                confidence=fuzzy_result.confidence,
                evidence=fuzzy_result.evidence
            )
        
        # Step 4: Try LLM match (with web search)
        llm_result = self._llm_match(nct_id, sponsor_text)
        if llm_result and llm_result.company_id:
            self.logger.info(f"NCT {nct_id}: LLM match found: {llm_result.company_id}")
            self._save_resolution(nct_id, sponsor_text, llm_result.company_id, "llm", llm_result.confidence, llm_result.evidence)
            
            # Save LLM discovery for learning
            self._save_llm_discovery(nct_id, sponsor_text, llm_result)
            
            return ResolutionOutput(
                company_id=llm_result.company_id,
                match_method="llm",
                confidence=llm_result.confidence,
                evidence=llm_result.evidence,
                aliases_discovered=llm_result.aliases_discovered
            )
        
        # Step 5: Add to manual review queue
        self.logger.info(f"NCT {nct_id}: No match found, adding to manual review: {sponsor_text}")
        self._add_to_review_queue(nct_id, sponsor_text)
        
        return ResolutionOutput(
            company_id=None,
            match_method="manual",
            confidence=0.0,
            evidence={"reason": "no_match_found", "sponsor": sponsor_text}
        )
    
    def _is_academic_sponsor(self, sponsor_text: str) -> bool:
        """Check if sponsor is academic using precise patterns."""
        # First check the old keyword method (for backward compatibility)
        if has_academic_keywords(sponsor_text):
            return True
        
        # Then check precise patterns from academic_blacklist
        try:
            result = self.session.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM academic_blacklist 
                        WHERE enabled = true 
                        AND :sponsor_text ~* pattern
                    )
                """),
                {"sponsor_text": sponsor_text}
            )
            return result.scalar_one()
        except Exception as e:
            self.logger.warning(f"Error checking academic blacklist: {e}")
            return False
    
    def _fuzzy_match(self, sponsor_text: str) -> Optional[ResolutionOutput]:
        """Try fuzzy matching using Jaro-Winkler similarity."""
        sponsor_norm = norm_name(sponsor_text)
        
        try:
            # Use PostgreSQL trigram similarity for fuzzy matching
            result = self.session.execute(
                text("""
                    SELECT 
                        c.company_id,
                        c.name,
                        c.name_norm,
                        similarity(c.name_norm, :sponsor_norm) as sim_score
                    FROM companies c
                    WHERE c.name_norm % :sponsor_norm
                    ORDER BY sim_score DESC
                    LIMIT 1
                """),
                {"sponsor_norm": sponsor_norm}
            )
            
            row = result.fetchone()
            if row and row.sim_score >= 0.8:  # High similarity threshold
                return ResolutionOutput(
                    company_id=row.company_id,
                    match_method="fuzzy",
                    confidence=row.sim_score,
                    evidence={
                        "method": "trigram_similarity",
                        "sponsor_norm": sponsor_norm,
                        "company_name": row.name,
                        "similarity_score": row.sim_score
                    }
                )
        except Exception as e:
            self.logger.warning(f"Error in fuzzy matching: {e}")
        
        return None
    
    def _llm_match(self, nct_id: str, sponsor_text: str) -> Optional[ResolutionOutput]:
        """Try LLM matching with web search for aliases/subsidiaries."""
        try:
            # Use centralized LLM system
            from ..llm import LLMProviderFactory, LLMRequest, LLMMessage, LLMGenerationConfig, LLMSchema
            
            # Create LLM factory and get provider for llm_resolution worker
            factory = LLMProviderFactory()
            provider = factory.create_for_worker("llm_resolution")
            model = factory.get_model_for_worker("llm_resolution")
            
            # Create system prompt
            system_prompt = """You are an expert clinical trial analyst specializing in pharmaceutical company identification.

Your task is to analyze sponsor information and determine:
1. Whether the sponsor is a publicly traded pharmaceutical/biotech company
2. The specific company name and details
3. Whether the trial should be included for investment analysis

Guidelines:
- Include trials sponsored by publicly traded pharmaceutical or biotech companies
- Exclude academic institutions, government agencies, hospitals, or non-profit organizations
- Use web search when available to verify company information
- Provide clear reasoning for your decisions
- Include confidence scores based on available evidence

Output your analysis as a structured JSON object with these fields:
- should_include: boolean
- reasoning: string
- sponsor_company: string (exact company name found)
- confidence_score: float (0.0-1.0)
- research_findings: string
- company_type: string (pharmaceutical, biotech, device, academic, government, other)
- stock_symbol: string (if available)
- alternative_names: array of strings (aliases, subsidiaries, etc.)"""

            # Create user prompt
            user_prompt = f"""Please analyze this clinical trial sponsor and determine if it should be included for investment analysis:

Sponsor: {sponsor_text}
NCT ID: {nct_id}

Research the sponsor company and provide a detailed analysis including:
1. Whether this is a publicly traded pharmaceutical/biotech company
2. The specific company details and stock symbol if available
3. Any alternative names, aliases, or subsidiaries
4. Your reasoning for inclusion/exclusion
5. Confidence level in your assessment

Respond with a JSON object containing your analysis."""

            # Create LLM request
            request = LLMRequest(
                model=model,
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt)
                ],
                generation_config=LLMGenerationConfig(
                    max_tokens=2000,
                    temperature=0.1
                ),
                schema=LLMSchema(
                    json_schema={
                        "type": "object",
                        "properties": {
                            "should_include": {"type": "boolean"},
                            "reasoning": {"type": "string"},
                            "sponsor_company": {"type": "string"},
                            "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "research_findings": {"type": "string"},
                            "company_type": {"type": "string", "enum": ["pharmaceutical", "biotech", "device", "academic", "government", "other"]},
                            "stock_symbol": {"type": "string"},
                            "alternative_names": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["should_include", "reasoning", "sponsor_company", "confidence_score", "research_findings", "company_type", "stock_symbol", "alternative_names"],
                        "additionalProperties": False
                    },
                    force=True
                )
            )
            
            # Make LLM call (sync version)
            import asyncio
            response = asyncio.run(provider.complete(request))
            
            # Parse response
            import json
            try:
                data = json.loads(response.content)
            except json.JSONDecodeError:
                self.logger.warning(f"Invalid JSON response from LLM: {response.content}")
                return None
            
            # Check if should include
            if data.get("should_include", False) and data.get("sponsor_company"):
                # Try to find company in database
                company = self._find_company_by_name(data["sponsor_company"])
                if company:
                    # Extract discovered aliases
                    aliases_discovered = data.get("alternative_names", [])
                    
                    return ResolutionOutput(
                        company_id=company.company_id,
                        match_method="llm",
                        confidence=data.get("confidence_score", 0.5),
                        evidence={
                            "method": "llm_web_search",
                            "llm_company": data["sponsor_company"],
                            "llm_response": data,
                            "research_findings": data.get("research_findings", ""),
                            "company_type": data.get("company_type", ""),
                            "stock_symbol": data.get("stock_symbol", "")
                        },
                        aliases_discovered=aliases_discovered
                    )
        
        except Exception as e:
            self.logger.warning(f"Error in LLM matching: {e}")
        
        return None
    
    def _find_company_by_name(self, company_name: str) -> Optional[Company]:
        """Find company by name using fuzzy matching."""
        try:
            # Try exact match first
            company = self.session.query(Company).filter(
                Company.name_norm == norm_name(company_name)
            ).first()
            
            if company:
                return company
            
            # Try fuzzy match
            result = self.session.execute(
                text("""
                    SELECT company_id FROM companies 
                    WHERE name_norm % :name_norm
                    ORDER BY similarity(name_norm, :name_norm) DESC
                    LIMIT 1
                """),
                {"name_norm": norm_name(company_name)}
            )
            
            row = result.fetchone()
            if row:
                return self.session.query(Company).filter(
                    Company.company_id == row.company_id
                ).first()
        
        except Exception as e:
            self.logger.warning(f"Error finding company by name: {e}")
        
        return None
    
    def _extract_aliases_from_llm(self, decision, metadata: Dict[str, Any]) -> List[str]:
        """Extract discovered aliases from LLM response."""
        aliases = []
        
        try:
            # Extract from research findings
            if decision.research_findings:
                # Simple extraction - look for company name variations
                findings = decision.research_findings.lower()
                if "also known as" in findings or "aka" in findings:
                    # Extract aliases (simplified)
                    pass
            
            # Extract from metadata
            if "llm_response" in metadata:
                llm_data = metadata["llm_response"]
                if isinstance(llm_data, dict):
                    # Look for alternative names
                    if "alternative_names" in llm_data:
                        aliases.extend(llm_data["alternative_names"])
        
        except Exception as e:
            self.logger.warning(f"Error extracting aliases: {e}")
        
        return aliases
    
    def _save_resolution(self, nct_id: str, sponsor_text: str, company_id: int, 
                        match_method: str, confidence: float, evidence: Dict[str, Any]):
        """Save resolution result to database."""
        try:
            resolution = SponsorResolution(
                nct_id=nct_id,
                sponsor_text=sponsor_text,
                sponsor_text_norm=norm_name(sponsor_text),
                company_id=company_id,
                match_method=match_method,
                confidence=confidence,
                evidence=evidence
            )
            self.session.add(resolution)
            self.session.commit()
        except Exception as e:
            self.logger.error(f"Error saving resolution: {e}")
            self.session.rollback()
    
    def _save_llm_discovery(self, nct_id: str, sponsor_text: str, result: ResolutionOutput):
        """Save LLM discovery for learning."""
        try:
            discovery = LLMDiscovery(
                nct_id=nct_id,
                sponsor_text=sponsor_text,
                discovered_company_id=result.company_id,
                discovered_aliases=result.aliases_discovered,
                llm_response=result.evidence,
                confidence=result.confidence
            )
            self.session.add(discovery)
            self.session.commit()
        except Exception as e:
            self.logger.error(f"Error saving LLM discovery: {e}")
            self.session.rollback()
    
    def _add_to_review_queue(self, nct_id: str, sponsor_text: str):
        """Add unresolved sponsor to manual review queue."""
        try:
            # Check if already in queue
            existing = self.session.query(ManualReviewQueue).filter(
                ManualReviewQueue.nct_id == nct_id,
                ManualReviewQueue.status == "pending"
            ).first()
            
            if not existing:
                review_item = ManualReviewQueue(
                    nct_id=nct_id,
                    sponsor_text=sponsor_text,
                    status="pending"
                )
                self.session.add(review_item)
                self.session.commit()
        except Exception as e:
            self.logger.error(f"Error adding to review queue: {e}")
            self.session.rollback()


def resolve_sponsor_simple(session: Session, nct_id: str, sponsor_text: str) -> ResolutionOutput:
    """
    Simple wrapper function for backward compatibility.
    
    Args:
        session: Database session
        nct_id: Clinical trial NCT ID
        sponsor_text: Raw sponsor text from trial
        
    Returns:
        ResolutionOutput with company match or manual review flag
    """
    resolver = SimpleResolver(session)
    return resolver.resolve_sponsor(nct_id, sponsor_text)
