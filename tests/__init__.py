"""Tests for the MyJDownloader integration."""

import importlib
import sys

try:
    import pytest_homeassistant  # noqa: F401
except ImportError:
    # Home Assistant publishes pytest-homeassistant from 2026.11 on. Older
    # versions are tested with its predecessor, which has the same modules.
    # Remove this once the minimum supported version is 2026.11.
    for _name in (
        "",
        ".common",
        ".components",
        ".components.diagnostics",
        ".syrupy",
        ".test_util",
        ".test_util.aiohttp",
        ".typing",
    ):
        sys.modules[f"pytest_homeassistant{_name}"] = importlib.import_module(
            f"pytest_homeassistant_custom_component{_name}"
        )
