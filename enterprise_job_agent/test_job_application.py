#!/usr/bin/env python3
"""
Test script for running job applications in test mode.
"""

import asyncio
import argparse
import logging
import json
import os
import sys
from datetime import datetime
import google.generativeai as genai
from crewai import Agent, Task, Crew, LLM
from crewai.agent import CrewAgentExecutor
from langchain_google_genai import ChatGoogleGenerativeAI

# Configure path for import resolution
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from enterprise_job_agent.main import run_job_application

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('job_application_test.log')
    ]
)

logger = logging.getLogger(__name__)

# Define the job URLs
JOB_URLS = {
    "discord": "https://job-boards.greenhouse.io/discord/jobs/7845336002",
    "remote": "https://job-boards.greenhouse.io/remotecom/jobs/6309578003",
    "allscripts": "https://boards.greenhouse.io/embed/job_app?for=allscripts&token=6507210003"
}

# Adjust paths to work regardless of which directory we're run from
def get_absolute_path(relative_path):
    """Convert a relative path to an absolute path based on the script location."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, relative_path)

async def run_job_test(
    job_key,
    profile_path="test_user/user_profile.json",
    visible=True,
    api_key=None,
    verbose=False
):
    """Run a test of a job application."""
    
    if job_key not in JOB_URLS:
        print(f"❌ Invalid job key: {job_key}")
        print(f"Valid options: {', '.join(JOB_URLS.keys())}")
        return False
    
    job_url = JOB_URLS[job_key]
    
    # Create a timestamp for uniqueness
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Ensure profile path is absolute
    if not os.path.isabs(profile_path):
        profile_path = get_absolute_path(profile_path)
    
    print(f"🧪 STARTING {job_key.upper()} JOB APPLICATION TEST - {timestamp}")
    print(f"🔗 Job URL: {job_url}")
    print(f"👤 Profile: {profile_path}")
    print(f"🖥️  Browser visible: {'Yes' if visible else 'No'}")
    print(f"📝 Verbose mode: {'Yes' if verbose else 'No'}")
    print("📢 Test Mode: Enabled (No actual submission will be made)")
    
    try:
        # Create output directory for this test
        test_dir = get_absolute_path(f"test_results/{job_key}_{timestamp}")
        os.makedirs(test_dir, exist_ok=True)
        
        # Run the job application in test mode
        result = await run_job_application(
            job_url=job_url,
            profile_path=profile_path,
            api_key=api_key,
            headless=not visible,
            test_mode=True,
            verbose=verbose
        )
        
        # Save test results
        results_file = f"{test_dir}/results.json"
        with open(results_file, "w") as f:
            json.dump(result, f, indent=2)
        
        print(f"📊 Results saved to {results_file}")
        
        if result["success"]:
            print(f"✅ {job_key.upper()} test completed successfully")
            print("\nForm fields processed:")
            
            # Extract and display field count statistics if available
            if "form_analysis" in result and "form_structure" in result["form_analysis"]:
                fields = []
                for section in result["form_analysis"]["form_structure"].get("sections", []):
                    fields.extend(section.get("fields", []))
                
                required_fields = [f for f in fields if f.get("required", False)]
                
                print(f"📋 Total fields: {len(fields)}")
                print(f"❗ Required fields: {len(required_fields)}")
                
                if "field_mappings" in result:
                    mappings = result["field_mappings"].get("field_mappings", [])
                    print(f"🔄 Mapped fields: {len(mappings)}")
                    
                    # Report on high-importance fields
                    high_importance = [m for m in mappings if m.get("importance") == "high"]
                    if high_importance:
                        print(f"⭐ High-importance fields: {len(high_importance)}")
            
            # Summary for the test run
            with open(f"{test_dir}/summary.txt", "w") as f:
                f.write(f"{job_key.upper()} JOB APPLICATION TEST - {timestamp}\n")
                f.write(f"Status: SUCCESS\n")
                f.write(f"URL: {job_url}\n")
                
                if "form_analysis" in result and "strategic_insights" in result["form_analysis"]:
                    f.write("\nSTRATEGIC INSIGHTS:\n")
                    for idx, insight in enumerate(result["form_analysis"]["strategic_insights"], 1):
                        f.write(f"{idx}. {insight}\n")
            
            return True
        else:
            print(f"❌ {job_key.upper()} test failed: {result.get('error', 'Unknown error')}")
            
            # Show recovery information if available
            if "recovery_result" in result:
                print("\n📋 Error Recovery Information:")
                diagnosis = result["recovery_result"].get("diagnosis", {})
                print(f"🔍 Error type: {diagnosis.get('error_type', 'Unknown')}")
                print(f"🔧 Root cause: {diagnosis.get('root_cause', 'Unknown')}")
                
                # Show selected approach
                selected = result["recovery_result"].get("selected_approach", "None")
                print(f"💡 Selected recovery approach: {selected}")
                
                # Save recovery information separately
                recovery_file = f"{test_dir}/recovery_info.json"
                with open(recovery_file, "w") as f:
                    json.dump(result["recovery_result"], f, indent=2)
                print(f"🔄 Recovery details saved to {recovery_file}")
            
            # Summary for the failed test run
            with open(f"{test_dir}/summary.txt", "w") as f:
                f.write(f"{job_key.upper()} JOB APPLICATION TEST - {timestamp}\n")
                f.write(f"Status: FAILED\n")
                f.write(f"URL: {job_url}\n")
                f.write(f"Error: {result.get('error', 'Unknown error')}\n")
            
            return False
    except Exception as e:
        logger.exception("Unhandled exception during test")
        print(f"❌ Test error: {e}")
        return False

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Job Application Test Tool")
    
    # Add subparsers for different job types
    subparsers = parser.add_subparsers(dest="job_type", help="Job to test: discord, remote, allscripts")
    subparsers.required = True
    
    # Discord job parser
    discord_parser = subparsers.add_parser("discord", help="Test Discord job application")
    _add_common_args(discord_parser)
    
    # Remote job parser
    remote_parser = subparsers.add_parser("remote", help="Test Remote.com job application")
    _add_common_args(remote_parser)
    
    # AllScripts job parser
    allscripts_parser = subparsers.add_parser("allscripts", help="Test AllScripts job application")
    _add_common_args(allscripts_parser)
    
    args = parser.parse_args()
    
    # Try to set up the CrewAI native Gemini integration
    setup_crewai_with_gemini(args.api_key)
    
    try:
        job_url = JOB_URLS.get(args.job_type)
        if not job_url:
            print(f"❌ Error: Unknown job type: {args.job_type}")
            sys.exit(1)
            
        success = asyncio.run(run_job_application_test(
            job_url=job_url,
            profile_path=args.profile,
            visible=args.visible,
            api_key=args.api_key,
            verbose=args.verbose
        ))
        
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ Test cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

def _add_common_args(parser):
    """Add common arguments to a parser."""
    parser.add_argument(
        "--profile", 
        type=str, 
        default="test_user/user_profile.json",
        help="Path to user profile JSON (default: test_user/user_profile.json)"
    )
    
    parser.add_argument(
        "--visible", 
        action="store_true", 
        help="Run with visible browser (default: headless)"
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

def setup_crewai_with_gemini(api_key=None):
    """
    Set up CrewAI to use Google's Gemini API natively through LiteLLM.
    
    Args:
        api_key: The API key for Gemini.
    """
    try:
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                print("⚠️ Warning: Gemini API key not provided. Set GEMINI_API_KEY environment variable.")
                return False
        
        # Create a LLM using CrewAI's native LLM class with correct LiteLLM format
        # Format for LiteLLM: 'gemini/gemini-2.0-flash'
        llm = LLM(
            model="gemini/gemini-2.0-flash",
            api_key=api_key,
            temperature=0.4,
        )
        
        print("✅ Successfully set up CrewAI with native Gemini 2.0 Flash integration")
        return llm
    except Exception as e:
        print(f"❌ Error setting up CrewAI with Gemini: {e}")
        return False

async def run_job_application_test(
    job_url: str,
    profile_path: str = "test_user/user_profile.json",
    visible: bool = False,
    api_key: str = None,
    verbose: bool = False
) -> bool:
    """
    Run a job application test with the specified parameters.
    
    Args:
        job_url: URL of the job posting
        profile_path: Path to user profile JSON
        visible: Whether to run with a visible browser
        api_key: API key for Gemini model
        verbose: Whether to enable verbose logging
        
    Returns:
        True if the test was successful, False otherwise
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_type = next((k for k, v in JOB_URLS.items() if v == job_url), "unknown")
    results_dir = f"enterprise_job_agent/test_results/{job_type}_{timestamp}"
    
    print(f"🧪 STARTING JOB APPLICATION TEST - {timestamp}")
    print(f"🔗 Job URL: {job_url}")
    
    # Ensure profile path is absolute
    if not os.path.isabs(profile_path):
        profile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), profile_path)
    
    print(f"👤 Profile: {profile_path}")
    print(f"🖥️  Browser visible: {'Yes' if visible else 'No'}")
    print(f"📢 Test Mode: Enabled (No actual submission will be made)")
    
    # Try to set up with the native Gemini LLM integration for CrewAI
    llm = setup_crewai_with_gemini(api_key)
    use_native_gemini = llm is not False
    
    try:
        # Import here to avoid circular imports
        from enterprise_job_agent.main import run_job_application
        
        # Run the job application in test mode
        result = await run_job_application(
            job_url=job_url,
            profile_path=profile_path,
            api_key=api_key,
            headless=not visible,
            test_mode=True,
            verbose=verbose,
            use_langchain_gemini=use_native_gemini,
            langchain_llm=llm
        )
        
        # Save test results
        os.makedirs(results_dir, exist_ok=True)
        results_file = os.path.join(results_dir, "results.json")
        with open(results_file, "w") as f:
            json.dump(result, f, indent=2)
        
        print(f"📊 Results saved to {results_file}")
        
        if result.get("success", False):
            print("✅ Test completed successfully!")
            return True
        else:
            error = result.get("error", "Unknown error")
            print(f"❌ Test failed: {error}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        return False

if __name__ == "__main__":
    main() 