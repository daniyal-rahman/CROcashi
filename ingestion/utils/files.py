import os
from pathlib import Path
from typing import Union


def ensure_dir(path: Union[str, Path]) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_text(path: Union[str, Path], content: str) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    p.write_text(content, encoding="utf-8")


def write_bytes(path: Union[str, Path], content: bytes) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    p.write_bytes(content)


