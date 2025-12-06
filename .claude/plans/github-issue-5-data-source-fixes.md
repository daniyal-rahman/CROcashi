# Plan: Fix Data Source Integration Issues (GitHub Issue #5)

## Summary

Three data sources are broken or suboptimal:
1. **PatentsView API** - Returns HTTP 410 (discontinued)
2. **OpenFDA Indication Extraction** - Extracts raw text instead of disease names
3. **FDA Drugs@FDA Download** - Website scraping broken (0 files found)

---

## Issue 1: PatentsView API Discontinued

### Current State
- File: `ingestion/patentsview.py`
- Endpoint: `https://api.patentsview.org/patents/query` returns `{"error":true, "reason":"discontinued"}`
- Impact: 0 patents in database

### Root Cause
USPTO PatentsView migrated to a new API in 2024. The old query API is discontinued.

### Solution: Migrate to New PatentsView API

The new PatentsView API uses a different endpoint and query structure:
- New base URL: `https://search.patentsview.org/api/v1/`
- Endpoints: `/patent/`, `/assignee/`, `/inventor/`
- Uses different query syntax (Elasticsearch-style)

### Implementation Steps

1. **Research new API structure**
   - Fetch API documentation from https://patentsview.org/apis/api-faqs
   - Identify equivalent endpoints for patent search
   - Understand new authentication requirements (if any)

2. **Update `ingestion/patentsview.py`**
   ```python
   # Change from:
   BASE_URL = "https://api.patentsview.org/patents/query"

   # To:
   BASE_URL = "https://search.patentsview.org/api/v1/patent/"
   ```

3. **Update query format**
   - Old: `{"q": {"_contains": {"patent_abstract": "pharma"}}}`
   - New: Uses path parameters and query strings

4. **Update response parsing**
   - Field names may have changed
   - Pagination structure different

5. **Test with pharmaceutical patent queries**
   - Search for patents with drug-related INN suffixes
   - Verify assignee/company extraction works

### Fallback Option
If new API is also problematic:
- Use USPTO Bulk Data downloads from https://bulkdata.uspto.gov/
- Download patent grant XML files and parse locally

---

## Issue 2: OpenFDA Indication Extraction Broken (HIGH PRIORITY)

### Current State
- File: `src/processors/openfda_processor.py`
- Method: `_extract_indications()` at line 250-280
- Method: `_parse_indication_text()` at line 285-322

### Root Cause
The `_parse_indication_text()` method is too simplistic:
```python
# Current behavior (problematic):
text = "INDICATIONS AND USAGE: For treatment of hypertension in adults..."
first_sentence = text.split('.')[0]  # Takes first sentence as-is
disease_name = first_sentence[:200]   # Truncates to 200 chars
# Result: disease_name = "INDICATIONS AND USAGE: For treatment of hypertension in adults"
```

This creates disease entities with names like:
- "Uses For handwashing to decrease bacteria on the skin"
- "INDICATIONS AND USAGE Ofloxacin ophthalmic solution is indicated for the treatment of..."

### Solution: Implement Medical Entity Recognition

#### Approach A: Pattern-Based Extraction (Simpler, Recommended First)

1. **Add indication text preprocessing**
   ```python
   def _clean_indication_text(self, text: str) -> str:
       """Remove boilerplate prefixes from indication text."""
       # Remove common prefixes
       prefixes_to_remove = [
           r'^INDICATIONS?\s*(AND\s*USAGE)?:?\s*',
           r'^Uses?\s*:?\s*',
           r'^(This\s+medication\s+is\s+)?indicated\s+for\s*:?\s*',
           r'^(This\s+medication\s+is\s+)?used\s+(for|to)\s+',
           r'^\d+\s+',  # Remove leading numbers like "1 "
       ]
       for pattern in prefixes_to_remove:
           text = re.sub(pattern, '', text, flags=re.IGNORECASE)
       return text.strip()
   ```

2. **Extract disease terms using patterns**
   ```python
   def _extract_disease_terms(self, text: str) -> List[str]:
       """Extract actual disease names from indication text."""
       diseases = []

       # Pattern: "treatment of [DISEASE]"
       # Pattern: "indicated for [DISEASE]"
       # Pattern: "used to treat [DISEASE]"
       patterns = [
           r'treatment\s+of\s+([A-Za-z\s]+?)(?:\s+in|\s+with|\s+for|,|\.)',
           r'indicated\s+for\s+(?:the\s+)?(?:treatment\s+of\s+)?([A-Za-z\s]+?)(?:\s+in|\s+with|,|\.)',
           r'used\s+to\s+treat\s+([A-Za-z\s]+?)(?:\s+in|\s+with|,|\.)',
           r'prevention\s+of\s+([A-Za-z\s]+?)(?:\s+in|\s+with|,|\.)',
       ]

       for pattern in patterns:
           matches = re.findall(pattern, text, re.IGNORECASE)
           diseases.extend(matches)

       return [d.strip() for d in diseases if len(d.strip()) > 3]
   ```

3. **Match against existing Disease entities**
   ```python
   def _match_disease(self, disease_term: str, session) -> Optional[Disease]:
       """Find matching disease in database using fuzzy matching."""
       # Exact match first
       disease = session.query(Disease).filter(
           func.lower(Disease.disease_name) == disease_term.lower()
       ).first()

       if disease:
           return disease

       # Check aliases
       disease = session.query(Disease).filter(
           Disease.aliases.contains([disease_term])
       ).first()

       if disease:
           return disease

       # Fuzzy match using trigram similarity (requires pg_trgm extension)
       # Or use Levenshtein distance

       return None
   ```

4. **Create new Disease only if no match found**
   - When creating new diseases, normalize the name
   - Store the original indication text in a `raw_indication` field for audit

#### Approach B: NLP-Based Extraction (More Accurate, More Complex)

If pattern-based approach insufficient:

1. **Add scispaCy for biomedical NER**
   ```bash
   pip install scispacy
   pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.1/en_core_sci_sm-0.5.1.tar.gz
   ```

2. **Use scispaCy to extract disease entities**
   ```python
   import spacy

   nlp = spacy.load("en_core_sci_sm")

   def _extract_diseases_nlp(self, text: str) -> List[str]:
       doc = nlp(text)
       diseases = []
       for ent in doc.ents:
           if ent.label_ in ('DISEASE', 'DISORDER', 'CONDITION'):
               diseases.append(ent.text)
       return diseases
   ```

3. **Use UMLS linking for normalization**
   - scispaCy can link to UMLS concepts
   - Map to ICD-10, MeSH, SNOMED codes

### Implementation Steps

1. **Add helper methods to OpenFDAProcessor**
   - `_clean_indication_text()` - Remove boilerplate
   - `_extract_disease_terms()` - Pattern-based extraction
   - `_normalize_disease_name()` - Standardize format

2. **Modify `_parse_indication_text()`**
   ```python
   def _parse_indication_text(self, text: str, raw_data: Dict) -> List[ExtractedEntity]:
       """Extract disease entities from indication text."""
       entities = []

       # Clean the text
       cleaned = self._clean_indication_text(text)

       # Extract disease terms
       disease_terms = self._extract_disease_terms(cleaned)

       for term in disease_terms:
           normalized = self._normalize_disease_name(term)
           if self.is_valid_entity_name(normalized):
               entities.append(ExtractedEntity(
                   entity_type=EntityType.DISEASE,
                   name=normalized,
                   identifiers={},
                   context={'raw_indication': text[:500]},
                   source_name='openfda',
                   source_identifier=self.get_source_identifier(raw_data),
                   raw_data=raw_data
               ))

       return entities
   ```

3. **Update `_extract_indications()` to use new method**

4. **Add disease normalization patterns**
   - Map common variations: "HTN" → "Hypertension"
   - Handle plural/singular: "cancers" → "cancer"
   - Remove qualifiers: "severe hypertension" → "hypertension" (keep severity in context)

5. **Add unit tests**
   - Test with real OpenFDA indication examples
   - Verify known diseases are extracted correctly
   - Test edge cases (empty text, boilerplate-only, multiple diseases)

6. **Run reprocessing**
   - Reprocess existing OpenFDA staging data
   - Verify drug_indications count increases significantly

### Success Criteria
- drug_indications count increases from 16 to 1000+
- Disease entities have proper names (not "INDICATIONS AND USAGE...")
- Extracted diseases match existing Disease entities where applicable

---

## Issue 3: FDA Drugs@FDA Download Broken (LOW PRIORITY)

### Current State
- File: `ingestion/fda_drugs.py`
- Method: `list_download_links()` finds 0 download links
- Impact: Cannot download bulk data files

### Root Cause
FDA website structure changed. The BeautifulSoup selectors no longer match.

### Solution Options

#### Option A: Fix Web Scraping (Not Recommended)
- Brittle; will break again when FDA updates their site
- Requires ongoing maintenance

#### Option B: Use OpenFDA API Exclusively (Recommended)
- `fda_applications_loader.py` already works
- Provides same data via API
- More stable than web scraping

#### Option C: Manual Download + Parse
- Download files manually from FDA website
- Place in `data/raw/fda_drugs/`
- Run parser only: `python -m ingestion.fda_drugs` (without --download)

### Implementation Steps

1. **Document the workaround**
   - Add note to README about using `fda_applications_loader.py`
   - Mark `fda_drugs.py --download` as deprecated

2. **Optional: Update scraper**
   - If FDA bulk data is still needed, inspect current FDA page structure
   - Update CSS selectors in `list_download_links()`

3. **Consider removing download functionality**
   - Keep only CSV/ZIP parsing for manual downloads
   - Rely on OpenFDA API for automated ingestion

---

## Priority Order

1. **HIGH: Fix OpenFDA Indication Extraction**
   - Impacts data quality significantly (only 16 drug_indications vs. thousands expected)
   - Pattern-based fix can be done quickly
   - Essential for drug-disease relationship analysis

2. **MEDIUM: Migrate PatentsView to New API**
   - 0 patents currently
   - New API research needed
   - Important for IP landscape analysis

3. **LOW: FDA Drugs Download**
   - Workaround exists (OpenFDA API via `fda_applications_loader.py`)
   - Web scraping is inherently brittle
   - Can be manual process if needed

---

## Files to Modify

| Priority | File | Changes |
|----------|------|---------|
| HIGH | `src/processors/openfda_processor.py` | Rewrite `_parse_indication_text()`, add helper methods |
| MEDIUM | `ingestion/patentsview.py` | Update API endpoint, query format, response parsing |
| LOW | `ingestion/fda_drugs.py` | Optional: update selectors or deprecate download |

---

## Testing Plan

### OpenFDA Indication Fix
```bash
# Run processor on small batch
python -c "
from src.processing.pipeline import ProcessingPipeline
pipeline = ProcessingPipeline()
stats = pipeline.process_source('openfda', limit=100)
print(stats)
"

# Verify drug_indications created
psql -c "SELECT COUNT(*) FROM drug_indications WHERE data_sources->>'openfda' IS NOT NULL"

# Check disease names are valid
psql -c "SELECT disease_name FROM diseases ORDER BY created_at DESC LIMIT 20"
```

### PatentsView Migration
```bash
# Test new API
python -c "
from ingestion.patentsview import search_patents
result = search_patents(limit=10)
print(f'Found {len(result.get(\"patents\", []))} patents')
"

# Verify patents loaded
psql -c "SELECT COUNT(*) FROM patents"
```

---

## Estimated Effort

| Issue | Complexity | Effort |
|-------|------------|--------|
| OpenFDA Indication | Medium | Pattern-based: a few focused changes |
| PatentsView API | Medium | API research + implementation |
| FDA Drugs Download | Low | Documentation or selector update |

---

## Questions for Discussion

1. **OpenFDA Indication Extraction:**
   - Should we use pattern-based or NLP-based approach first?
   - How should we handle multi-indication drugs (e.g., aspirin for pain AND heart attack prevention)?
   - Should we create new Disease entities or only match existing ones?

2. **PatentsView:**
   - Is patent data critical for current use cases?
   - Should we explore alternative sources (Google Patents, USPTO bulk)?

3. **FDA Drugs:**
   - Is bulk download still needed given OpenFDA API works?
   - Should we deprecate the download functionality entirely?
