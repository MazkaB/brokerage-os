"""Test configuration.

All tests use a temporary DB / Chroma dir so they never touch real data.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Make the BOS package importable when running pytest from project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _isolate_env(tmp_path_factory):
    """Point all storage at a temp dir for the duration of the test session."""
    base = tmp_path_factory.mktemp("bos_test")
    db_path = base / "bos.db"
    chroma_path = base / "chroma"
    kb_path = ROOT / "knowledge_base"

    os.environ["BOS_DB_PATH"] = str(db_path)
    os.environ["BOS_CHROMA_PATH"] = str(chroma_path)
    os.environ["BOS_KB_PATH"] = str(kb_path)
    os.environ.setdefault("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", "test-key"))

    # Reset cached singletons so they pick up the new paths
    from app.config import get_settings
    get_settings.cache_clear()
    yield
