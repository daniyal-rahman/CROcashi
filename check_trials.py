#!/usr/bin/env python3
"""Check available trials in database."""

from dotenv import load_dotenv
load_dotenv()

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.db.session import get_session
from ncfd.db.models import Trial

def main():
    with get_session() as session:
        trials = session.query(Trial).limit(10).all()
        print("Available trials:")
        for trial in trials:
            title = trial.brief_title or "No title"
            print(f"- {trial.nct_id}: {title[:60]}...")

if __name__ == "__main__":
    main()
