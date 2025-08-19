# ncfd/src/ncfd/ingest/deps.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class DepStatus:
    bs4: bool
    lxml: bool
    pdfminer: bool

def check() -> DepStatus:
    try:
        import bs4  # noqa
        has_bs4 = True
    except Exception:
        has_bs4 = False
    try:
        import lxml  # noqa
        has_lxml = True
    except Exception:
        has_lxml = False
    try:
        import pdfminer  # noqa
        has_pdf = True
    except Exception:
        has_pdf = False
    return DepStatus(has_bs4, has_lxml, has_pdf)

def human_message() -> str:
    s = check()
    msg = []
    msg.append(f"beautifulsoup4: {'OK' if s.bs4 else 'MISSING'}")
    msg.append(f"lxml          : {'OK' if s.lxml else 'MISSING'}")
    msg.append(f"pdfminer.six  : {'OK' if s.pdfminer else 'MISSING'}")
    if not (s.bs4 and s.lxml):
        msg.append("HTML parsing will be degraded. Install: pip install beautifulsoup4 lxml")
    if not s.pdfminer:
        msg.append("PDF parsing disabled. Install: pip install pdfminer.six")
    return "\n".join(msg)
