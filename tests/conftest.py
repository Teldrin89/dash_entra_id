import os
import sys
import tempfile
from pathlib import Path

# Must be set before `app` is imported (config.py reads the environment at import time).
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("AZURE_TENANT_ID", "11111111-aaaa-bbbb-cccc-222222222222")
os.environ.setdefault("AZURE_CLIENT_ID", "test-client-id")
os.environ.setdefault("AZURE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("SESSION_FILE_DIR", tempfile.mkdtemp())
os.environ.pop("AUTH_MODE", None)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from cachelib import SimpleCache

from app import create_app


@pytest.fixture
def make_app():
    """Build an isolated app (own in-memory session store); kwargs override config."""
    def _make(**overrides):
        overrides.setdefault("SESSION_CACHELIB", SimpleCache())
        return create_app(overrides)
    return _make
