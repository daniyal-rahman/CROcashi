"""
LLM-based Trial Resolution Service

Migrated version of llm_decider using the new modular LLM system.
Provides enhanced LLM decision making with independent research capabilities.
"""

import os
import json
import requests
from typing import Dict, Any, Tuple, Optional, List
from dataclasses import dataclass
from datetime import datetime
import logging

from ..llm import LLMProviderFactory, LLMRequest, LLMMessage, LLMGenerationConfig, LLMSchema
from .normalize import has_academic_keywords
from .models import LlmDecision

logger = logging.getLogger(__name__)


@dataclass
class ClinicalTrialMetadata:
    """Metadata for a clinical trial from ClinicalTrials.gov."""
    nct_id: str
    title: str
    sponsor: str
    status: str
    phase: str
    start_date: Optional[str]
    completion_date: Optional[str]
    condition: str
    intervention: str
    raw_data: Dict[str, Any]


class LLMTrialResolver:
    """
    LLM-based trial resolution service using modular provider system.
    
    Handles company resolution for clinical trials with enhanced research capabilities.
    Uses configurable LLM providers (OpenAI, Anthropic, Gemini).
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the LLM resolver."""
        self.llm_factory = LLMProviderFactory(config)
        self.llm_provider = self.llm_factory.create_for_worker("llm_decider")
        self.model = self.llm_factory.get_model_for_worker("llm_decider")
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"LLM Trial Resolver initialized with provider={self.llm_provider.provider_name}, model={self.model}")
    
    async def decide_with_llm_research(
        self,
        run_id: str,
        nct_id: str,
        session,
        context: Dict[str, Any],
    ) -> Tuple[LlmDecision, Dict[str, Any]]:
        """
        Enhanced LLM decision with independent research capabilities.
        
        Args:
            run_id: Execution run ID
            nct_id: ClinicalTrials.gov NCT ID
            session: Database session
            context: Additional context
            
        Returns:
            Tuple of (LlmDecision, metadata)
        """
        # Step 1: Fetch ClinicalTrials.gov metadata
        trial_metadata = await self._fetch_ctgov_metadata(nct_id)
        if not trial_metadata:
            # Log the failure and fallback to basic mock decision
            await self._log_llm_attempt(
                run_id=run_id,
                nct_id=nct_id,
                sponsor_text="unknown_sponsor",
                success=False,
                error_msg="Failed to fetch ClinicalTrials.gov metadata",
                session=session,
                model=self.model
            )
            return self._mock_llm_decision_research(nct_id, session)
        
        # Step 1.5: Check for academic/government sponsors
        if has_academic_keywords(trial_metadata.sponsor):
            self.logger.info(f"NCT {nct_id}: Academic/government sponsor detected: {trial_metadata.sponsor}")
            decision = LlmDecision(
                should_include=False,
                reasoning="Academic or government sponsor detected",
                sponsor_company=trial_metadata.sponsor,
                confidence_score=0.95,
                llm_provider=self.llm_provider.provider_name,
                llm_model=self.model
            )
            return decision, {"trial_metadata": trial_metadata.__dict__}
        
        # Step 2: Create LLM prompts
        system_prompt = self._create_system_prompt()
        user_prompt = self._create_enhanced_user_prompt(nct_id, trial_metadata)
        
        try:
            # Make LLM call using new abstraction
            messages = [
                LLMMessage(role="user", content=user_prompt)
            ]
            
            # Use JSON schema for structured output
            json_schema = {
                "type": "object",
                "properties": {
                    "should_include": {"type": "boolean"},
                    "reasoning": {"type": "string"},
                    "sponsor_company": {"type": "string"},
                    "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "research_findings": {"type": "string"},
                    "company_type": {"type": "string", "enum": ["pharmaceutical", "biotech", "device", "academic", "government", "other"]},
                    "stock_symbol": {"type": "string"}
                },
                "required": ["should_include", "reasoning", "sponsor_company", "confidence_score"]
            }
            
            request = LLMRequest(
                model=self.model,
                messages=messages,
                system=system_prompt,
                generation_config=LLMGenerationConfig(
                    max_tokens=2000,
                    temperature=0.1
                ),
                schema=LLMSchema(
                    json_schema=json_schema,
                    force=True
                )
            )
            
            # Add web search tools for GPT-5 models if supported
            if "gpt-5" in self.model.lower():
                from ..llm.models import LLMTool
                request.tools = [
                    LLMTool(
                        name="web_search",
                        description="Search the web for current information",
                        parameters={"type": "object", "properties": {}}
                    )
                ]
            
            response = await self.llm_provider.complete(request)
            
            # Parse response
            try:
                data = json.loads(response.content)
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON response: {response.content}")
            
            # Create LLM decision
            decision = LlmDecision(
                should_include=data.get("should_include", False),
                reasoning=data.get("reasoning", "No reasoning provided"),
                sponsor_company=data.get("sponsor_company", trial_metadata.sponsor),
                confidence_score=data.get("confidence_score", 0.5),
                llm_provider=self.llm_provider.provider_name,
                llm_model=self.model,
                research_findings=data.get("research_findings"),
                company_type=data.get("company_type"),
                stock_symbol=data.get("stock_symbol")
            )
            
            # Log successful attempt
            await self._log_llm_attempt(
                run_id=run_id,
                nct_id=nct_id,
                sponsor_text=trial_metadata.sponsor,
                success=True,
                error_msg=None,
                raw_data={"trial_metadata": trial_metadata.__dict__, "llm_response": data},
                session=session,
                model=self.model
            )
            
            return decision, {"trial_metadata": trial_metadata.__dict__, "llm_response": data}
            
        except Exception as e:
            self.logger.error(f"LLM call failed for {nct_id}: {e}")
            
            # Log the API failure
            await self._log_llm_attempt(
                run_id=run_id,
                nct_id=nct_id,
                sponsor_text=trial_metadata.sponsor,
                success=False,
                error_msg=f"LLM API call failed: {e}",
                raw_data={"trial_metadata": trial_metadata.__dict__},
                session=session,
                model=self.model
            )
            
            return self._mock_llm_decision_research(nct_id, session)
    
    async def _fetch_ctgov_metadata(self, nct_id: str) -> Optional[ClinicalTrialMetadata]:
        """Fetch trial metadata from ClinicalTrials.gov API v2."""
        try:
            url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract key fields from API structure
            protocol_section = data.get("protocolSection", {})
            sponsor_module = protocol_section.get("sponsorCollaboratorsModule", {})
            lead_sponsor = sponsor_module.get("leadSponsor", {})
            sponsor = lead_sponsor.get("name", "")
            
            identification_module = protocol_section.get("identificationModule", {})
            title = identification_module.get("briefTitle", "")
            
            status_module = protocol_section.get("statusModule", {})
            status = status_module.get("overallStatus", "")
            start_date = status_module.get("startDateStruct", {}).get("date")
            completion_date = status_module.get("completionDateStruct", {}).get("date")
            
            design_module = protocol_section.get("designModule", {})
            phases = design_module.get("phases", [])
            phase = phases[0] if phases else "Not Applicable"
            
            conditions_module = protocol_section.get("conditionsModule", {})
            conditions = conditions_module.get("conditions", [])
            condition = conditions[0] if conditions else ""
            
            interventions_module = protocol_section.get("armsInterventionsModule", {})
            interventions = interventions_module.get("interventions", [])
            intervention = interventions[0].get("name", "") if interventions else ""
            
            return ClinicalTrialMetadata(
                nct_id=nct_id,
                title=title,
                sponsor=sponsor,
                status=status,
                phase=phase,
                start_date=start_date,
                completion_date=completion_date,
                condition=condition,
                intervention=intervention,
                raw_data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to fetch metadata for {nct_id}: {e}")
            return None
    
    def _create_system_prompt(self) -> str:
        """Create the system prompt for LLM decision making."""
        return """You are an expert clinical trial analyst specializing in pharmaceutical company identification and trial relevance assessment.

Your task is to analyze clinical trial information and determine:
1. Whether the trial is sponsored by a publicly traded pharmaceutical/biotech company
2. The specific company name and details
3. Whether the trial should be included for investment analysis

Guidelines:
- Include trials sponsored by publicly traded pharmaceutical or biotech companies
- Exclude academic institutions, government agencies, hospitals, or non-profit organizations
- Use web search when available to verify company information
- Provide clear reasoning for your decisions
- Include confidence scores based on available evidence

Output your analysis as a structured JSON object."""
    
    def _create_enhanced_user_prompt(self, nct_id: str, trial_metadata: ClinicalTrialMetadata) -> str:
        """Create enhanced user prompt with trial metadata."""
        data = {
            "nct_id": nct_id,
            "title": trial_metadata.title,
            "sponsor": trial_metadata.sponsor,
            "status": trial_metadata.status,
            "phase": trial_metadata.phase,
            "condition": trial_metadata.condition,
            "intervention": trial_metadata.intervention,
            "start_date": trial_metadata.start_date,
            "completion_date": trial_metadata.completion_date
        }
        
        return f"""Please analyze this clinical trial and determine if it should be included for investment analysis:

Trial Information:
{json.dumps(data, indent=2, ensure_ascii=False)}

Research the sponsor company if needed and provide a detailed analysis including:
1. Whether this is a publicly traded pharmaceutical/biotech company
2. The specific company details and stock symbol if available
3. Your reasoning for inclusion/exclusion
4. Confidence level in your assessment

Respond with a JSON object containing your analysis."""
    
    def _mock_llm_decision_research(self, nct_id: str, session) -> Tuple[LlmDecision, Dict[str, Any]]:
        """Create a mock decision when LLM is unavailable."""
        decision = LlmDecision(
            should_include=False,
            reasoning="LLM service unavailable, defaulting to exclusion",
            sponsor_company="Unknown",
            confidence_score=0.0,
            llm_provider="mock",
            llm_model="mock"
        )
        
        return decision, {"mock": True, "nct_id": nct_id}
    
    async def _log_llm_attempt(
        self,
        run_id: str,
        nct_id: str,
        sponsor_text: str,
        success: bool,
        error_msg: Optional[str] = None,
        raw_data: Optional[Dict[str, Any]] = None,
        session=None,
        model: str = "unknown"
    ):
        """Log LLM attempt to database."""
        # This would integrate with your existing logging system
        log_data = {
            "run_id": run_id,
            "nct_id": nct_id,
            "sponsor_text": sponsor_text,
            "success": success,
            "error_msg": error_msg,
            "raw_data": raw_data,
            "model": model,
            "timestamp": datetime.now()
        }
        
        self.logger.info(f"LLM attempt logged: {log_data}")
        # TODO: Implement actual database logging
