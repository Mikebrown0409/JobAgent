#!/usr/bin/env python3
"""
Test script for running job applications in test mode using pytest.
"""

import asyncio
# import argparse # Removed
import logging
import json
import os
import sys
from datetime import datetime
import pytest # Added pytest import
# Removed unused CrewAI/Langchain imports unless needed for fixtures later

# Configure path for import resolution
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from enterprise_job_agent.main import analyze_job_application

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('job_application_pytest.log') # Changed log file name
    ]
)

logger = logging.getLogger(__name__)

# Define the job URLs and keys
JOB_KEYS = ["discord", "remote", "allscripts"] # Define keys for parametrization
JOB_URLS = {
    "discord": "https://job-boards.greenhouse.io/discord/jobs/7845336002",
    "remote": "https://job-boards.greenhouse.io/remotecom/jobs/6309578003",
    "allscripts": "https://boards.greenhouse.io/embed/job_app?for=allscripts&token=6507210003"
}

# Default profile path (can be overridden via CLI or fixtures)
DEFAULT_PROFILE_PATH = "test_user/user_profile.json"

# Adjust paths to work regardless of which directory we're run from
def get_absolute_path(relative_path):
    """Convert a relative path to an absolute path based on the script location."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, relative_path)

@pytest.mark.parametrize("job_key", JOB_KEYS) # Parameterize over job keys
@pytest.mark.asyncio # Mark the test function as async
async def test_single_job_application( # Renamed function to start with test_
    job_key,
    pytestconfig # Access pytest config for options
):
    """Runs analyze_job_application for a single job key in test mode."""
    profile_path = pytestconfig.getoption("profile")
    visible = pytestconfig.getoption("visible")
    verbose = pytestconfig.getoption("verbose") > 0 # Check verbosity level
    
    # Use default profile if not provided
    if not profile_path:
        profile_path = DEFAULT_PROFILE_PATH
        
    if job_key not in JOB_URLS:
        pytest.fail(f"❌ Invalid job key parameterized: {job_key}") # Use pytest.fail
    
    job_url = JOB_URLS[job_key]
    
    # Create a timestamp for uniqueness
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Ensure profile path is absolute
    if not os.path.isabs(profile_path):
        profile_path = get_absolute_path(profile_path)
    
    print(f"\n🧪 STARTING {job_key.upper()} JOB APPLICATION TEST - {timestamp}")
    print(f"🔗 Job URL: {job_url}")
    print(f"👤 Profile: {profile_path}")
    print(f"🖥️  Browser visible: {'Yes' if visible else 'No'}")
    print(f"📝 Verbose mode: {'Yes' if verbose else 'No'}")
    print("📢 Test Mode: Enabled (No actual submission will be made)")
    
    try:
        # Create output directory for this test run
        test_dir = get_absolute_path(f"test_results/pytest_{job_key}_{timestamp}") # Prefix with pytest_
        os.makedirs(test_dir, exist_ok=True)
        
        # Run the job application analysis
        result = await analyze_job_application(
            url=job_url,
            user_profile_path=profile_path,
            visible=visible,
            test_mode=True,
            verbose=verbose,
            output_dir=test_dir
        )
        
        # Save test results
        results_file = f"{test_dir}/results.json"
        with open(results_file, "w") as f:
            json.dump(result, f, indent=2)
        
        print(f"📊 Results saved to {results_file}")
        
        # Use pytest assertion
        assert result.get("success", False) is True, f"{job_key.upper()} test failed: {result.get('error', 'Unknown error')}"
        
        print(f"✅ {job_key.upper()} test completed successfully")
        # Optional: Print summary stats if needed for quick view
        # ... (summary printing logic can remain if desired) ...
        
    except Exception as e:
        logger.exception(f"Unhandled exception during test for {job_key}")
        pytest.fail(f"❌ Test error for {job_key}: {e}") # Use pytest.fail

# Removed pytest_addoption hook - moved to conftest.py
# Removed unused main() and _add_common_args() functions 