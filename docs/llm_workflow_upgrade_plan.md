# LLM Workflow Upgrade Plan

## Overview

Upgrade the LLM resolver to use GPT-5's internet access for independent research on clinical trials and companies, aiming for 95% overall matching accuracy.

## Design Decisions & Choices

### 1. Research Scope
- **ClinicalTrials.gov**: Full trial record (all metadata fields)
- **Google Search**: Comprehensive company research (ticker, domain, pipeline, recent news)
- **Company Research**: Focus on biotech/pharma companies, ticker symbols, website domains, recent clinical trial activity

### 2. Output Format
- **Company ID**: Return our internal company_id when possible, fallback to company name/details
- **Confidence**: 0.0-1.0 scale with detailed reasoning
- **Evidence**: URLs, quotes, reasoning chain, match confidence breakdown
- **Match Type**: exact, high_confidence, moderate_confidence, low_confidence, uncertain

### 3. Integration Points
- **Company Matching**: LLM research findings map to existing company database via fuzzy matching
- **Fallback**: Human review when LLM can't find match or has low confidence
- **Validation**: Still run deterministic/probabilistic as sanity check and for training data

### 4. Technical Implementation
- **API Calls**: Use GPT-5's built-in web search capabilities
- **Rate Limiting**: Monitor usage, implement basic rate limiting if needed
- **Caching**: No caching for now (future enhancement)
- **Error Handling**: Graceful fallback to human review

## Workflow Design

### Enhanced Resolution Cascade
```
1. Deterministic Resolution
   ├── Try exact alias/company/domain matches
   ├── Try rule-based regex patterns
   └── If match found → ACCEPT and return

2. Probabilistic Resolution
   ├── Extract features and score candidates
   ├── Apply trained model weights
   └── Check against thresholds

3. LLM Research Resolution (NEW)
   ├── Fetch full ClinicalTrials.gov record
   ├── LLM researches sponsor independently
   ├── Web search for company information
   ├── Generate confidence prediction
   └── Map to our company database

4. Human Review (Fallback)
   ├── When all automated methods fail
   ├── Human expert makes final decision
   └── Generates training data for improvement
```

### LLM Research Process
```
Input: NCT ID
↓
1. Fetch ClinicalTrials.gov Metadata
   ├── Sponsor information
   ├── Trial details
   ├── Phase, indication, dates
   └── Full trial record

2. LLM Web Research
   ├── Search for sponsor company
   ├── Research company details
   ├── Find ticker, domain, pipeline
   └── Gather evidence

3. Company Matching
   ├── Fuzzy match to our database
   ├── Confidence scoring
   ├── Evidence compilation
   └── Decision generation

4. Output
   ├── Company ID (if found)
   ├── Confidence score
   ├── Research evidence
   └── Reasoning chain
```

## Implementation Plan

### Phase 1: Enhanced LLM Decider
1. **Modify `llm_decider.py`**
   - Add ClinicalTrials.gov API integration
   - Enhance prompts for research capabilities
   - Implement comprehensive output parsing

2. **Update CLI Functions**
   - Modify cascade logic to include LLM research
   - Ensure proper fallback to human review
   - Maintain training data generation

### Phase 2: Company Matching
1. **Fuzzy Matching Logic**
   - Implement company name matching
   - Handle variations and aliases
   - Confidence scoring for matches

2. **Evidence Compilation**
   - URL collection and validation
   - Quote extraction and storage
   - Reasoning chain documentation

### Phase 3: Integration & Testing
1. **Database Schema Updates**
   - Store research evidence
   - Track LLM research decisions
   - Maintain audit trail

2. **Testing & Validation**
   - Test with various trial types
   - Validate accuracy improvements
   - Monitor API usage

## Technical Specifications

### ClinicalTrials.gov Integration
- **API**: Use ClinicalTrials.gov API v2
- **Fields**: Full trial record including sponsor, phase, indication, dates
- **Rate Limiting**: Respect API limits, implement backoff

### GPT-5 Web Search
- **Capabilities**: Leverage built-in web search
- **Prompts**: Structured research prompts with clear output format
- **Fallback**: Handle search failures gracefully

### Company Database Integration
- **Matching**: Fuzzy string matching with confidence scoring
- **Validation**: Cross-reference with existing company data
- **Updates**: Allow LLM to suggest new company additions

## Expected Outcomes

### Accuracy Improvements
- **Current**: ~70-80% automated resolution
- **Target**: 95% overall matching accuracy
- **Method**: LLM research + existing deterministic/probabilistic

### Efficiency Gains
- **Reduced Human Review**: More trials resolved automatically
- **Better Training Data**: LLM decisions provide additional training examples
- **Faster Resolution**: LLM research faster than manual investigation

### Data Quality
- **Comprehensive Evidence**: Research-backed decisions with URLs and quotes
- **Audit Trail**: Full decision chain documented
- **Training Enhancement**: Rich feature vectors for model improvement

## Risk Mitigation

### API Usage
- **Monitoring**: Track API calls and costs
- **Fallbacks**: Graceful degradation when APIs fail
- **Rate Limiting**: Implement basic throttling if needed

### Accuracy Concerns
- **Validation**: Cross-check LLM decisions with existing methods
- **Confidence Thresholds**: Only accept high-confidence LLM decisions
- **Human Oversight**: Maintain human review for uncertain cases

### Data Quality
- **Evidence Validation**: Verify URLs and quotes
- **Company Matching**: Robust fuzzy matching with confidence scoring
- **Audit Trail**: Complete decision documentation

## Success Metrics

### Primary Metrics
- **Resolution Rate**: Percentage of trials resolved automatically
- **Accuracy**: Correct company matches / total matches
- **Human Review Reduction**: Decrease in trials requiring manual review

### Secondary Metrics
- **API Usage**: Cost and rate limit monitoring
- **Processing Time**: Time to resolution for different methods
- **Training Data Quality**: Improvement in probabilistic model performance

## Implementation Timeline

### Week 1: Core LLM Research
- Implement ClinicalTrials.gov API integration
- Enhance LLM prompts for research
- Basic company matching logic

### Week 2: Integration & Testing
- Integrate with existing cascade
- Test with sample trials
- Validate accuracy improvements

### Week 3: Refinement & Deployment
- Optimize prompts and matching
- Deploy to production
- Monitor performance and usage

## Future Enhancements

### Caching & Optimization
- Cache ClinicalTrials.gov responses
- Implement intelligent rate limiting
- Optimize prompt engineering

### Advanced Features
- Multi-language support
- Company relationship mapping
- Pipeline and asset tracking

### Monitoring & Analytics
- Detailed performance metrics
- A/B testing for prompt optimization
- Automated accuracy validation
