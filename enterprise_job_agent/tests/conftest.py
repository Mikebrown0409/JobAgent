"""Test configuration for pytest."""

import os
import sys
from pathlib import Path

# Add the project root directory to Python path
project_root = str(Path(__file__).parent.parent.parent)
sys.path.append(project_root)

# --- Pytest Fixtures ---

import pytest
import asyncio
from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager

@pytest.fixture(scope="function") # Can change scope later if needed (e.g., "module")
async def browser_manager_fixture():
    """Pytest fixture to manage BrowserManager lifecycle for tests."""
    # Minimal diagnostics for tests unless specifically needed
    diagnostics_manager = DiagnosticsManager(output_dir="test_results/diagnostics") 
    
    # Initialize BrowserManager (headless by default for tests)
    browser_manager = BrowserManager(visible=False, diagnostics_manager=diagnostics_manager)
    
    try:
        await browser_manager.initialize()
        yield browser_manager # Provide the initialized manager to the test
    finally:
        # Ensure browser is closed after the test finishes
        await browser_manager.close() 