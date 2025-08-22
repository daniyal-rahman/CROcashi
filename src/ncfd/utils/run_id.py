from datetime import datetime, timezone

def make_run_id() -> str:
    # e.g., 20250818T052310Z
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
