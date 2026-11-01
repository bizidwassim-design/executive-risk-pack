from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture()
def data_copy(tmp_path: Path) -> Path:
    """A writable copy of data/ that a test can break on purpose."""
    dst = tmp_path / "data"
    shutil.copytree(ROOT / "data", dst)
    return dst


def replace_in(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path.name}"
    path.write_text(text.replace(old, new, count), encoding="utf-8", newline="\n")
