import pytest

def pytest_addoption(parser):
    """Add custom command-line options to pytest."""
    parser.addoption(
        "--profile", action="store", default=None, help="Path to the user profile JSON/YAML file"
    )
    parser.addoption(
        "--visible", action="store_true", default=False, help="Show browser window"
    )
    # --verbose is handled by pytest, use -v 