"""Conftest: mock unavailable third-party packages before any test imports."""

import sys
from unittest.mock import MagicMock

# anthropic and voyageai are not installed on Python 3.14.
# Mock them so that modules with top-level imports can be loaded.
for mod_name in ("anthropic", "voyageai"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()
