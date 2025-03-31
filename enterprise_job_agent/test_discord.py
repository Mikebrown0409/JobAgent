#!/usr/bin/env python3
"""
Test the job application process with a Discord job posting.
"""

import os
import sys
import asyncio
import argparse
import logging
import json
from datetime import datetime

# Configure path for import resolution
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Local imports
from enterprise_job_agent.main import run_job_application, initialize_llm
from enterprise_job_agent.config import JOB_URLS

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('discord_test.log')
    ]
)

logger = logging.getLogger(__name__)

def get_job_url(job_type):
    """Get the job URL for the specified job type."""
    # Default to Discord job URL if not specified or not found
    if not job_type or job_type not in JOB_URLS:
        logger.info(f"Using default Discord job URL: {JOB_URLS['discord']}")
        return JOB_URLS['discord']
    
    logger.info(f"Using {job_type} job URL: {JOB_URLS[job_type]}")
    return JOB_URLS[job_type]

async def run_job_test(job_type='discord', visible=False, profile_path=None, api_key=None, verbose=False):
    """
    Run a test of the job application process.
    
    Args:
        job_type: Type of job to apply for (e.g. 'discord', 'google', etc.)
        visible: Whether to run with a visible browser
        profile_path: Path to user profile JSON
        api_key: API key for the model
        verbose: Whether to enable verbose logging
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_url = get_job_url(job_type)
    
    print(f"🧪 STARTING JOB APPLICATION TEST - {timestamp}")
    print(f"🔗 Job URL: {job_url}")
    logger.info(f"Starting job application test for {job_type} with URL {job_url}")
    
    if not profile_path:
        profile_path = os.path.join(current_dir, "test_user/user_profile.json")
    
    print(f"👤 Profile: {profile_path}")
    print(f"🖥️  Browser visible: {'Yes' if visible else 'No'}")
    print(f"📢 Test Mode: Enabled (No actual submission will be made)")
    
    try:
        # Run the job application process
        logger.info("Calling run_job_application function")
        result = await run_job_application(
            job_url=job_url,
            profile_path=profile_path,
            api_key=api_key,
            headless=not visible,
            test_mode=True,
            verbose=verbose,
            use_together=False  # Use default Gemini model, not Together AI
        )
        
        if result.get("success", False):
            print("✅ Test completed successfully!")
            print(f"📊 Results saved to {result.get('report_file', 'Unknown location')}")
            logger.info(f"Test completed successfully. Results saved to {result.get('report_file')}")
            return True
        else:
            error = result.get("error", "Unknown error")
            print(f"❌ Test failed: {error}")
            logger.error(f"Test failed: {error}")
            return False
    
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        logger.exception(f"Test failed with exception: {str(e)}")
        return False

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Job Application Test")
    
    parser.add_argument(
        "--job-type",
        type=str,
        default="discord",
        help="Type of job to apply for (default: discord)"
    )
    
    parser.add_argument(
        "--visible", 
        action="store_true", 
        help="Run with visible browser (default: headless)"
    )
    
    parser.add_argument(
        "--profile", 
        type=str, 
        help="Path to user profile JSON (default: test_user/user_profile.json)"
    )
    
    parser.add_argument(
        "--api-key", 
        type=str, 
        help="Gemini API key (can also be set via GEMINI_API_KEY environment variable)"
    )
    
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    try:
        success = asyncio.run(run_job_test(
            job_type=args.job_type,
            visible=args.visible,
            profile_path=args.profile,
            api_key=args.api_key,
            verbose=args.verbose
        ))
        
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ Test cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.exception(f"Unhandled exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 