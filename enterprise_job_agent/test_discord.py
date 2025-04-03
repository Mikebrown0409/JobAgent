#!/usr/bin/env python3
"""
Test script for the Discord job application process.
"""

import os
import sys
import json
import asyncio
import argparse
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# Add parent directory to path to import enterprise_job_agent modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enterprise_job_agent.main import analyze_job_application

async def run_test(visible: bool = False, verbose: bool = False):
    """Run a test of the job application process on Discord's job site."""
    # Discord job URL - Software Engineer job
    job_url = "https://job-boards.greenhouse.io/discord/jobs/7845336002"
    
    # Create a temporary output directory
    output_dir = Path(__file__).parent / "test_results"
    
    # Run the job application process in test mode
    result = await analyze_job_application(
        url=job_url,
        test_mode=True,
        visible=visible,
        output_dir=str(output_dir),
        verbose=verbose
    )
    
    # Check if test was successful
    if result.get("success", False) is False and "error" in result:
        print(f"❌ Test failed: {result['error']}")
        return False
    
    # Check if any fields were actually filled
    fields_filled = result.get("execution_results", {}).get("fields_filled", 0)
    fields_failed = result.get("execution_results", {}).get("fields_failed", 0)
    total_fields = fields_filled + fields_failed
    
    if fields_filled == 0 and total_fields > 0:
        print(f"❌ Test failed: No fields were filled successfully (0/{total_fields})")
        return False
    
    print("✅ Test completed successfully!")
    print(f"📊 Results saved to {result.get('results_dir', 'Unknown location')}")
    print(f"Fields filled: {fields_filled}/{total_fields}")
    return True

def main():
    """Main entry point for the test script."""
    parser = argparse.ArgumentParser(description="Test Discord Job Application")
    parser.add_argument("--visible", action="store_true", help="Run with visible browser")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        success = asyncio.run(run_test(visible=args.visible, verbose=args.verbose))
        if not success:
            sys.exit(1)
    except Exception as e:
        logging.error(f"Error running test: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 