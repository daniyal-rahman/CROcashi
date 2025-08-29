# PubMed Client Specification

## Overview
This document specifies the PubMed client implementation for handling E-utilities API calls with proper rate limiting, batching, and error handling.

## API Endpoints

### Base URLs
- **ESearch**: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi`
- **ESummary**: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi`
- **EFetch**: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi`
- **ELink**: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi`

## Rate Limiting & Quotas

### Without API Key
- **Limit**: 3 requests per second
- **Daily cap**: 10,000 requests
- **Strategy**: 333ms minimum delay between requests

### With API Key
- **Limit**: 10 requests per second
- **Daily cap**: 100,000 requests
- **Strategy**: 100ms minimum delay between requests

### Batch Processing
- **ESearch**: up to 100 PMIDs per request
- **ESummary**: up to 500 PMIDs per request
- **EFetch**: up to 500 PMIDs per request

## Request Patterns

### Stage U0: Discovery
```
1. ESearch(query) → PMID list + count
2. ESummary(PMID batch) → metadata
3. Insert documents with status='discovered'
```

### Stage U1: Abstract Fetch
```
1. EFetch(PMID batch, rettype=abstract) → abstract text
2. Update document_text.abstract_text
3. Extract entities and score R/S
```

### Stage OA: Full Text (Optional)
```
1. ELink(pmid→pmcid) → PMC ID if available
2. Check PMC OA status
3. EFetch(pmcid, rettype=text) → full text
```

## Error Handling

### Retry Strategy
- **Exponential backoff**: 1s, 2s, 4s, 8s delays
- **Max retries**: 3 attempts per request
- **Circuit breaker**: pause for 60s after 5 consecutive failures

### Common Errors
- **429 Too Many Requests**: increase delay, respect Retry-After header
- **503 Service Unavailable**: exponential backoff
- **500 Internal Error**: retry with delay
- **400 Bad Request**: log and skip (query issue)

## Response Processing

### ESearch Response
- Extract PMID list and total count
- Handle pagination if >100 results
- Parse error messages for query issues

### ESummary Response
- Extract title, journal, pub date, article type
- Parse MeSH terms and substance names
- Handle missing fields gracefully

### EFetch Response
- Extract abstract text (clean HTML/XML)
- Handle encoding issues (UTF-8, ISO-8859-1)
- Validate text length and quality

## Configuration

### Environment Variables
- `PUBMED_API_KEY`: NCBI API key for higher limits
- `PUBMED_RATE_LIMIT`: custom rate limit (requests/second)
- `PUBMED_BATCH_SIZE`: custom batch size for requests

### Config File Settings
```yaml
pubmed:
  api_key: ${PUBMED_API_KEY}
  rate_limit_per_sec: 8
  batch_size: 100
  max_retries: 3
  timeout_seconds: 30
  backoff_base: 2.0
  circuit_breaker_threshold: 5
```

## Monitoring & Logging

### Metrics to Track
- Requests per second
- Success/failure rates
- Response times
- Rate limit hits
- Daily request counts

### Logging
- Request/response logging for debugging
- Error details for failed requests
- Performance metrics for optimization
