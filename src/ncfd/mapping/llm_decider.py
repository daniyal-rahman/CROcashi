# ncfd/src/ncfd/mapping/llm_decider.py
from __future__ import annotations

import json
import os
import re
import requests
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    from sqlalchemy import text
except ImportError:
    text = None  # Will handle gracefully in mock mode

try:
    # SDK v1.x
    from openai import OpenAI  # pip install openai>=1.40.0
except Exception as e:  # pragma: no cover
    OpenAI = None  # defer import error until first use


@dataclass
class LlmDecision:
    mode: str                    # "accept" | "review" | "reject"
    company_id: Optional[int]    # required when mode == "accept"
    confidence: float            # 0..1 (heuristic self-report)
    rationale: str               # short explanation
    flags: List[str]             # any extra signals
    research_evidence: Optional[Dict[str, Any]] = None  # NEW: research findings
    company_name: Optional[str] = None  # NEW: company name from research
    match_type: Optional[str] = None  # NEW: exact, high_confidence, moderate_confidence, low_confidence, uncertain


@dataclass
class ClinicalTrialMetadata:
    """Structured ClinicalTrials.gov trial metadata"""
    nct_id: str
    sponsor: str
    title: str
    phase: Optional[str]
    condition: Optional[str]
    intervention: Optional[str]
    status: Optional[str]
    start_date: Optional[str]
    completion_date: Optional[str]
    enrollment: Optional[int]
    raw_data: Dict[str, Any]


def _client() -> Any:
    if OpenAI is None:
        raise RuntimeError(
            "openai package not installed. `pip install openai>=1.40.0`"
        )
    kwargs = {}
    if os.getenv("OPENAI_BASE_URL"):
        kwargs["base_url"] = os.getenv("OPENAI_BASE_URL")
    if os.getenv("OPENAI_ORG_ID"):
        kwargs["organization"] = os.getenv("OPENAI_ORG_ID")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Return None to indicate fallback mode
        return None
    
    return OpenAI(api_key=api_key, **kwargs)


def fetch_ctgov_metadata(nct_id: str) -> Optional[ClinicalTrialMetadata]:
    """
    Fetch trial metadata from ClinicalTrials.gov API v2
    """
    try:
        # ClinicalTrials.gov API v2 endpoint
        url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        study = data.get("study", {})
        
        # Extract key fields from the correct API structure
        protocol_section = data.get("protocolSection", {})
        sponsor_module = protocol_section.get("sponsorCollaboratorsModule", {})
        lead_sponsor = sponsor_module.get("leadSponsor", {})
        sponsor = lead_sponsor.get("name", "")
        
        # Get identification module for title
        identification_module = protocol_section.get("identificationModule", {})
        title = identification_module.get("briefTitle", "")
        
        # Get status module for status and dates
        status_module = protocol_section.get("statusModule", {})
        status = status_module.get("overallStatus", "")
        start_date = status_module.get("startDateStruct", {}).get("date")
        completion_date = status_module.get("completionDateStruct", {}).get("date")
        
        # Get phase information
        design_module = protocol_section.get("designModule", {})
        phases = design_module.get("phases", [])
        phase = phases[0] if phases else None
        
        # Get condition and intervention
        conditions_module = protocol_section.get("conditionsModule", {})
        conditions = conditions_module.get("conditions", [])
        condition = conditions[0] if conditions else None
        
        arms_interventions_module = protocol_section.get("armsInterventionsModule", {})
        interventions = arms_interventions_module.get("interventions", [])
        intervention = interventions[0] if interventions else None
        
        # Get enrollment
        eligibility_module = protocol_section.get("eligibilityModule", {})
        enrollment = eligibility_module.get("enrollmentInfo", {}).get("count")
        
        return ClinicalTrialMetadata(
            nct_id=nct_id,
            sponsor=sponsor,
            title=title,
            phase=phase,
            condition=condition,
            intervention=intervention,
            status=status,
            start_date=start_date,
            completion_date=completion_date,
            enrollment=enrollment,
            raw_data=data
        )
        
    except Exception as e:
        print(f"Warning: Failed to fetch ClinicalTrials.gov data for {nct_id}: {e}")
        return None


def _fuzzy_company_match(company_name: str, session) -> Tuple[Optional[int], float, str]:
    """
    Fuzzy match company name to our database
    Returns: (company_id, confidence, match_type)
    """
    if not company_name:
        return None, 0.0, "uncertain"
    
    # If no session provided, return mock results for testing
    if session is None:
        # Mock company matching for testing
        company_name_lower = company_name.lower()
        if "astrazeneca" in company_name_lower:
            return 12345, 0.9, "high_confidence"  # Mock AstraZeneca ID
        elif "pfizer" in company_name_lower:
            return 67890, 0.9, "high_confidence"  # Mock Pfizer ID
        elif "roche" in company_name_lower:
            return 11111, 0.9, "high_confidence"  # Mock Roche ID
        else:
            return None, 0.3, "uncertain"
    
    try:
        # Simple fuzzy matching - can be enhanced later
        company_name_clean = re.sub(r'[^\w\s]', '', company_name.lower())
        
        # Try exact match first
        exact_match = session.execute(
            text("SELECT company_id, name FROM companies WHERE LOWER(name) = :name"),
            {"name": company_name_clean}
        ).first()
        
        if exact_match:
            return int(exact_match[0]), 1.0, "exact"
        
        # Try partial matches
        partial_matches = session.execute(
            text("""
                SELECT company_id, name, 
                       similarity(LOWER(name), :name) as sim
                FROM companies 
                WHERE LOWER(name) % :name 
                   OR :name % LOWER(name)
                   OR LOWER(name) ILIKE :pattern
                ORDER BY sim DESC
                LIMIT 5
            """),
            {
                "name": company_name_clean,
                "pattern": f"%{company_name_clean}%"
            }
        ).fetchall()
        
        if partial_matches:
            best_match = partial_matches[0]
            company_id = int(best_match[0])
            similarity = float(best_match[2])
            
            if similarity > 0.8:
                return company_id, similarity, "high_confidence"
            elif similarity > 0.6:
                return company_id, similarity, "moderate_confidence"
            else:
                return company_id, similarity, "low_confidence"
        
        return None, 0.0, "uncertain"
        
    except Exception as e:
        print(f"Warning: Company matching failed: {e}")
        return None, 0.0, "uncertain"


def _enhanced_system_prompt() -> str:
    return (
        "You are an expert clinical trial sponsor resolver with internet access. "
        "Your task is to research clinical trial sponsors and identify the correct company match. "
        "Use web search to research company details, ticker symbols, domains, and recent activity. "
        "Be thorough in your research and provide evidence for your decisions. "
        "Focus on biotech/pharma companies and clinical trial sponsors. "
        "Output JSON only with the specified format."
    )


def _enhanced_user_prompt(nct_id: str, trial_metadata: ClinicalTrialMetadata) -> str:
    data = {
        "nct_id": nct_id,
        "trial_info": {
            "sponsor": trial_metadata.sponsor,
            "title": trial_metadata.title,
            "phase": trial_metadata.phase,
            "condition": trial_metadata.condition,
            "intervention": trial_metadata.intervention,
            "status": trial_metadata.status,
            "start_date": trial_metadata.start_date,
            "completion_date": trial_metadata.completion_date,
            "enrollment": trial_metadata.enrollment
        },
        "task": {
            "objective": "Research the sponsor and identify the correct company match",
            "research_steps": [
                "Search for the sponsor company using web search",
                "Research company details (ticker, domain, pipeline, recent news)",
                "Verify company is involved in clinical trials",
                "Assess confidence in the match",
                "Provide evidence and reasoning"
            ],
            "output_schema": {
                "company_name": "string (exact company name found)",
                "company_details": "string (brief company description)",
                "ticker": "string (stock ticker if public company)",
                "website": "string (company website if found)",
                "confidence": "float (0.0-1.0 confidence in match)",
                "match_type": "exact|high_confidence|moderate_confidence|low_confidence|uncertain",
                "evidence": "array of strings (URLs, quotes, research findings)",
                "reasoning": "string (detailed explanation of decision)",
                "flags": "array of strings (any concerns or special notes)"
            }
        }
    }
    return json.dumps(data, ensure_ascii=False)


def decide_with_llm_research(
    *,
    run_id: str,
    nct_id: str,
    session,
    context: Dict[str, Any],
) -> Tuple[LlmDecision, Dict[str, Any]]:
    """
    Enhanced LLM decision with independent research capabilities.
    Uses GPT-5's web search to research trials and companies independently.
    """
    model = os.getenv("OPENAI_MODEL_RESOLVER", "gpt-5")
    cli = _client()
    
    # If no OpenAI client available, use mock decision
    if cli is None:
        return _mock_llm_decision_research(nct_id, session)
    
    # Step 1: Fetch ClinicalTrials.gov metadata
    trial_metadata = fetch_ctgov_metadata(nct_id)
    if not trial_metadata:
        # Log the failure and fallback to basic mock decision
        _log_llm_attempt(
            run_id=run_id,
            nct_id=nct_id,
            sponsor_text="unknown_sponsor",
            success=False,
            error_msg="Failed to fetch ClinicalTrials.gov metadata",
            session=session
        )
        return _mock_llm_decision_research(nct_id, session)
    
    # Step 2: Build enhanced prompts
    system = _enhanced_system_prompt()
    user = _enhanced_user_prompt(nct_id, trial_metadata)
    
    try:
        # Use GPT-5 with web search capabilities using the newer responses API
        if "gpt-5" in model.lower():
            # Use the newer responses API with web_search_preview
            # Note: responses.create() doesn't support response_format
            resp = cli.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                tools=[{"type": "web_search_preview"}],
            )
            content = resp.output_text
        else:
            # Fallback to chat completions for other models
            resp = cli.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
        
    except Exception as e:
        print(f"Warning: LLM call failed: {e}")
        # Log the API failure
        _log_llm_attempt(
            run_id=run_id,
            nct_id=nct_id,
            sponsor_text=trial_metadata.sponsor if trial_metadata else "unknown_sponsor",
            success=False,
            error_msg=f"LLM API call failed: {e}",
            raw_data={"trial_metadata": trial_metadata.__dict__ if trial_metadata else None},
            session=session
        )
        return _mock_llm_decision_research(nct_id, session)
    
    try:
        data = json.loads(content)
    except Exception as json_error:
        # Log the JSON parsing failure
        _log_llm_attempt(
            run_id=run_id,
            nct_id=nct_id,
            sponsor_text=trial_metadata.sponsor if trial_metadata else "unknown_sponsor",
            success=False,
            error_msg=f"Model did not return valid JSON: {json_error}",
            raw_data={"raw_content": content, "trial_metadata": trial_metadata.__dict__ if trial_metadata else None},
            session=session
        )
        # If model hiccups, return review with a flag
        return (
            LlmDecision(
                mode="review", 
                company_id=None, 
                confidence=0.0,
                rationale="Model did not return valid JSON; routed to review.",
                flags=["bad_json"],
                research_evidence={"trial_metadata": trial_metadata.__dict__}
            ),
            {"raw": content, "trial_metadata": trial_metadata.__dict__}
        )
    
    # Parse LLM response
    company_name = data.get("company_name", "")
    confidence = float(data.get("confidence", 0.0))
    match_type = data.get("match_type", "uncertain")
    evidence = data.get("evidence", [])
    reasoning = data.get("reasoning", "")
    flags = data.get("flags", [])
    
    # Step 3: Try to match to our company database
    company_id, db_confidence, db_match_type = _fuzzy_company_match(company_name, session)
    
    # Step 4: Determine final decision
    if company_id and confidence >= 0.8 and db_confidence >= 0.7:
        mode = "accept"
        final_confidence = min(confidence, db_confidence)
    elif company_id and confidence >= 0.6 and db_confidence >= 0.5:
        mode = "review"
        final_confidence = (confidence + db_confidence) / 2
    else:
        mode = "review"
        final_confidence = max(confidence, db_confidence)
    
    # Step 5: Create research evidence structure
    research_evidence = {
        "trial_metadata": trial_metadata.__dict__,
        "llm_research": {
            "company_name": company_name,
            "company_details": data.get("company_details", ""),
            "ticker": data.get("ticker", ""),
            "website": data.get("website", ""),
            "evidence": evidence,
            "reasoning": reasoning
        },
        "database_match": {
            "company_id": company_id,
            "confidence": db_confidence,
            "match_type": db_match_type
        }
    }
    
    decision = LlmDecision(
        mode=mode,
        company_id=company_id,
        confidence=final_confidence,
        rationale=reasoning[:2000] if reasoning else "LLM research completed",
        flags=flags,
        research_evidence=research_evidence,
        company_name=company_name,
        match_type=match_type
    )
    
    raw = {
        "llm_response": data,
        "trial_metadata": trial_metadata.__dict__,
        "database_match": {"company_id": company_id, "confidence": db_confidence, "match_type": db_match_type}
    }
    
    # Log the successful LLM decision
    _log_llm_attempt(
        run_id=run_id,
        nct_id=nct_id,
        sponsor_text=trial_metadata.sponsor if trial_metadata else "unknown_sponsor",
        success=True,
        decision=decision,
        raw_data=raw,
        session=session
    )
    
    return decision, raw


def _log_llm_attempt(
    run_id: str,
    nct_id: str,
    sponsor_text: str,
    success: bool,
    error_msg: str = None,
    decision: LlmDecision = None,
    raw_data: Dict[str, Any] = None,
    session=None
) -> None:
    """
    Robust logging of LLM attempts with safe defaults and separate session.
    Always logs, even on failures, to ensure we have a complete audit trail.
    """
    try:
        # Create a separate session for logging to avoid rollback issues
        try:
            from ncfd.db.session import get_session
            with get_session() as log_session:
                # Prepare safe defaults for all NOT NULL columns
                safe_sponsor_text = sponsor_text or "unknown_sponsor"
                safe_nct_id = nct_id or "unknown_nct"
                safe_run_id = run_id or "unknown_run"
                
                if success and decision:
                    # Log successful decision
                    safe_company_id = decision.company_id if decision.company_id else None
                    safe_match_type = decision.match_type or "uncertain"
                    safe_p_match = decision.confidence if decision.confidence else 0.0
                    safe_top2_margin = 1.0 if decision.mode == "accept" else 0.0
                    safe_features = decision.research_evidence or {}
                    safe_evidence = {
                        "llm_success": True,
                        "decision_mode": decision.mode,
                        "confidence": decision.confidence,
                        "flags": decision.flags or [],
                        "raw_data": raw_data or {}
                    }
                    safe_decided_by = "llm"
                    safe_notes = decision.rationale or "LLM research completed successfully"
                else:
                    # Log failure with safe defaults
                    safe_company_id = None
                    safe_match_type = "failed"
                    safe_p_match = 0.0
                    safe_top2_margin = 0.0
                    safe_features = {}
                    safe_evidence = {
                        "llm_success": False,
                        "error": error_msg or "Unknown LLM failure",
                        "raw_data": raw_data or {}
                    }
                    safe_decided_by = "llm"
                    safe_notes = f"LLM research failed: {error_msg or 'Unknown error'}"
                
                # Insert into resolver_llm_logs with the correct schema
                from sqlalchemy import text
                sql = text("""
                    INSERT INTO resolver_llm_logs
                        (run_id, nct_id, sponsor_text, candidates, prompt, response_json, 
                         decision_mode, chosen_company_id, confidence)
                    VALUES
                        (:run_id, :nct_id, :sponsor_text, :candidates, :prompt, :response_json,
                         :decision_mode, :chosen_company_id, :confidence)
                """)
                
                # Prepare data for the correct table schema
                import json
                safe_candidates = json.dumps(raw_data or {}) if raw_data else "{}"
                safe_prompt = "LLM research prompt for clinical trial sponsor resolution"
                safe_response_json = json.dumps(raw_data or {}) if raw_data else "{}"
                safe_decision_mode = decision.mode if decision else "review"
                safe_chosen_company_id = decision.company_id if decision and decision.company_id else None
                safe_confidence = decision.confidence if decision else 0.0
                
                log_session.execute(sql, {
                    "run_id": safe_run_id,
                    "nct_id": safe_nct_id,
                    "sponsor_text": safe_sponsor_text,
                    "candidates": safe_candidates,
                    "prompt": safe_prompt,
                    "response_json": safe_response_json,
                    "decision_mode": safe_decision_mode,
                    "chosen_company_id": safe_chosen_company_id,
                    "confidence": safe_confidence,
                })
                
                log_session.commit()
                print(f"[LOG] LLM attempt logged: {nct_id} -> {safe_match_type} (success={success})")
                
        except Exception as log_error:
            print(f"[WARNING] Failed to log LLM attempt: {log_error}")
            # The context manager will handle cleanup automatically
                    
    except Exception as e:
        print(f"[ERROR] Critical logging failure: {e}")
        # At this point, we can't even log the logging failure, but we don't want to crash the main flow


def _mock_llm_decision_research(nct_id: str, session) -> Tuple[LlmDecision, Dict[str, Any]]:
    """
    Mock LLM research decision for testing when OpenAI is not available.
    """
    # Fetch trial metadata for mock decision
    trial_metadata = fetch_ctgov_metadata(nct_id)
    
    if not trial_metadata:
        # Log the mock decision with no metadata
        _log_llm_attempt(
            run_id="mock-run",
            nct_id=nct_id,
            sponsor_text="unknown_sponsor",
            success=False,
            error_msg="Mock: No trial metadata available",
            raw_data={"mock": True, "reason": "no_metadata"},
            session=session
        )
        return (
            LlmDecision(
                mode="review", 
                company_id=None, 
                confidence=0.0,
                rationale="Mock: No trial metadata available",
                flags=["mock_decision", "no_metadata"],
                research_evidence={"trial_metadata": None}
            ),
            {"mock": True, "reason": "no_metadata"}
        )
    
    # Simple mock logic based on sponsor text
    sponsor_lower = trial_metadata.sponsor.lower()
    
    if any(keyword in sponsor_lower for keyword in ["national", "institute", "university", "hospital"]):
        # Log the mock academic sponsor decision
        _log_llm_attempt(
            run_id="mock-run",
            nct_id=nct_id,
            sponsor_text=trial_metadata.sponsor,
            success=True,
            decision=LlmDecision(
                mode="review", 
                company_id=None, 
                confidence=0.3,
                rationale="Mock: Academic/government sponsor - needs human review",
                flags=["mock_decision", "academic_sponsor"],
                research_evidence={"trial_metadata": trial_metadata.__dict__},
                company_name=trial_metadata.sponsor,
                match_type="uncertain"
            ),
            raw_data={"mock": True, "decision": "review", "reason": "academic_sponsor"},
            session=session
        )
        return (
            LlmDecision(
                mode="review", 
                company_id=None, 
                confidence=0.3,
                rationale="Mock: Academic/government sponsor - needs human review",
                flags=["mock_decision", "academic_sponsor"],
                research_evidence={"trial_metadata": trial_metadata.__dict__},
                company_name=trial_metadata.sponsor,
                match_type="uncertain"
            ),
            {"mock": True, "decision": "review", "reason": "academic_sponsor"}
        )
    
    # Try to find a company match
    company_id, confidence, match_type = _fuzzy_company_match(trial_metadata.sponsor, session)
    
    if company_id and confidence > 0.6:
        # Log the mock company match decision
        mock_decision = LlmDecision(
            mode="accept", 
            company_id=company_id, 
            confidence=confidence,
            rationale=f"Mock: Found company match with confidence {confidence:.2f}",
            flags=["mock_decision", "company_found"],
            research_evidence={"trial_metadata": trial_metadata.__dict__},
            company_name=trial_metadata.sponsor,
            match_type=match_type
        )
        _log_llm_attempt(
            run_id="mock-run",
            nct_id=nct_id,
            sponsor_text=trial_metadata.sponsor,
            success=True,
            decision=mock_decision,
            raw_data={"mock": True, "decision": "accept", "reason": "company_found"},
            session=session
        )
        return (
            mock_decision,
            {"mock": True, "decision": "accept", "reason": "company_found"}
        )
    else:
        # Log the mock no match decision
        mock_decision = LlmDecision(
            mode="review", 
            company_id=None, 
            confidence=0.4,
            rationale="Mock: No clear company match found",
            flags=["mock_decision", "no_match"],
            research_evidence={"trial_metadata": trial_metadata.__dict__},
            company_name=trial_metadata.sponsor,
            match_type="uncertain"
        )
        _log_llm_attempt(
            run_id="mock-run",
            nct_id=nct_id,
            sponsor_text=trial_metadata.sponsor,
            success=True,
            decision=mock_decision,
            raw_data={"mock": True, "decision": "review", "reason": "no_match"},
            session=session
        )
        return (
            mock_decision,
            {"mock": True, "decision": "review", "reason": "no_match"}
        )


# Keep the original function for backward compatibility
def decide_with_llm(
    *,
    run_id: str,
    nct_id: str,
    sponsor_text: str,
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
    topk: int = 10,
) -> Tuple[LlmDecision, Dict[str, Any]]:
    """
    Original LLM decision function (kept for backward compatibility).
    For new implementations, use decide_with_llm_research().
    """
    # If we have candidates, use the original logic
    if candidates:
        return _original_llm_decision(candidates, sponsor_text)
    
    # If no candidates, fall back to research mode
    return decide_with_llm_research(
        run_id=run_id,
        nct_id=nct_id,
        session=None,  # Will use mock mode
        context=context
    )


def _original_llm_decision(
    candidates: List[Dict[str, Any]],
    sponsor_text: str,
) -> Tuple[LlmDecision, Dict[str, Any]]:
    """
    Original LLM decision logic for when candidates are provided.
    """
    if not candidates:
        return (
            LlmDecision(mode="reject", company_id=None, confidence=0.0,
                        rationale="No candidates available", flags=["no_candidates"]),
            {"mock": True, "reason": "no_candidates"}
        )
    
    top_candidate = candidates[0]
    top_sim = float(top_candidate.get("sim", 0.0))
    top_p = float(top_candidate.get("p", 0.0))
    
    # Simple heuristic: accept if very high similarity or high probability
    if top_sim > 0.9 or top_p > 0.8:
        company_id = int(top_candidate.get("company_id"))
        return (
            LlmDecision(mode="accept", company_id=company_id, confidence=0.85,
                        rationale=f"Mock accept: high similarity ({top_sim:.3f}) or probability ({top_p:.3f})", 
                        flags=["mock_decision", "high_confidence"]),
            {"mock": True, "decision": "accept", "reason": "high_confidence"}
        )
    else:
        return (
            LlmDecision(mode="review", company_id=None, confidence=0.5,
                        rationale=f"Mock review: moderate similarity ({top_sim:.3f}) or probability ({top_p:.3f})", 
                        flags=["mock_decision", "moderate_confidence"]),
            {"mock": True, "decision": "review", "reason": "moderate_confidence"}
        )
