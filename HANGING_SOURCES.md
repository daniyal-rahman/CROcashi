# Sources That Hang or Timeout

## Known Hanging Sources

### fda_faers
- **Issue**: Function `try_download_recent()` hangs when trying to download FAERS files
- **Reason**: The function tries multiple quarters (8 attempts) with 2 patterns each, making up to 16 HTTP requests. Each request can take a long time or hang if the server is slow/unresponsive.
- **Location**: `ingestion/fda_faers.py`
- **Status**: SKIPPED in tests - needs optimization (reduce attempts, add per-request timeout, or use async)

### wayback_machine
- **Issue**: Function `get_snapshots()` times out (>15s)
- **Reason**: Wayback Machine CDX API can be slow or unresponsive for some URLs
- **Location**: `ingestion/wayback_machine.py`
- **Status**: TIMEOUT in tests - needs investigation (may need longer timeout or different API endpoint)

---

## Failed Sources (Non-Timeouts)

### pubchem
- **Issue**: API call fails with error
- **Location**: `ingestion/pubchem.py`
- **Status**: FAILED - needs API endpoint verification

### sec_edgar
- **Issue**: Test script bug - missing required argument
- **Location**: `ingestion/sec_edgar.py` (test script fixed)
- **Status**: FIXED - test script updated

---

## Notes
- These sources are marked as hanging/failing during testing
- They should be fixed or optimized before production use
- Consider adding request-level timeouts or reducing the number of attempts
- Test results: 39/42 sources working successfully

