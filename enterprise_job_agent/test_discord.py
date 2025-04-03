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
from typing import Dict, Any, Optional

# Add parent directory to path to import enterprise_job_agent modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.agents.form_analyzer_agent import FormAnalyzerAgent
from enterprise_job_agent.agents.profile_adapter_agent import ProfileAdapterAgent
from enterprise_job_agent.core.action_executor import ActionExecutor
from enterprise_job_agent.agents.application_executor_agent import ApplicationExecutorAgent
from enterprise_job_agent.main import execute_form

# Import CrewAI LLM
from crewai import LLM

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Initialize LLM
def initialize_llm():
    """Initialize LLM for testing."""
    # Check for API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("No GEMINI_API_KEY found in environment. Please set it before running the test.")
        sys.exit(1)
    
    # Initialize LLM
    return LLM(
        model="gemini/gemini-2.0-flash",
        api_key=api_key,
        temperature=0.2
    )

# Create test profile
def create_test_profile():
    """Create a test user profile."""
    # Base directory for test data
    test_data_dir = os.path.join(os.path.dirname(__file__), "test_data")
    
    return {
        "personal_info": {
            "first_name": "Alex",
            "last_name": "Chen",
            "email": "alex.chen@example.com",
            "phone": "555-123-4567",
            "location": {
                "city": "San Francisco",
                "state": "California",
                "country": "United States"
            }
        },
        "resume_path": os.path.join(test_data_dir, "resume.txt"),
        "cover_letter_path": os.path.join(test_data_dir, "cover_letter.txt"),
        "education": [
            {
                "school": "University of California, Berkeley",
                "degree": "Bachelor of Science",
                "field_of_study": "Computer Science",
                "graduation_date": "2021-05-15"
            }
        ]
    }

# Print execution results
def print_execution_results(results: Dict[str, Any]):
    """Print execution results in a readable format."""
    fields_filled = results.get("fields_filled", 0)
    fields_failed = results.get("fields_failed", 0)
    field_results = results.get("field_results", [])
    field_type_stats = results.get("field_type_stats", {})
    
    total_fields = fields_filled + fields_failed
    
    print("\n===== FIELD EXECUTION RESULTS =====")
    print(f"Fields filled: {fields_filled}/{total_fields}")
    print(f"Fields failed: {fields_failed}")
    print()
    
    # Print field type statistics
    print("Field Type Statistics:")
    for field_type, stats in field_type_stats.items():
        success_rate = (stats["success"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        print(f"  {field_type}: {stats['success']}/{stats['total']} successful ({success_rate:.1f}%)")
    print()
    
    # Print detailed field results
    print("Detailed Field Results:")
    for result in field_results:
        field_id = result.get("field_id", "")
        success = result.get("success", False)
        field_type = result.get("field_type", "unknown")
        
        if success:
            value = result.get("value", "")
            # Truncate long values
            if isinstance(value, str) and len(value) > 30:
                value = value[:27] + "..."
            print(f"  ✓ {field_id} ({field_type}): {value}")
        else:
            error = result.get("error", "Unknown error")
            print(f"  ✗ {field_id} ({field_type}): ERROR: {error}")

# Main test function
async def test_discord_application(args):
    """Test Discord job application process."""
    # Create output directory for results
    test_results_dir = os.path.join(os.path.dirname(__file__), "test_results")
    job_id = f"job_a34a82b5"  # Fixed ID for test
    results_dir = os.path.join(test_results_dir, job_id)
    os.makedirs(results_dir, exist_ok=True)
    
    # Setup diagnostics
    diagnostics_manager = DiagnosticsManager(
        output_dir=os.path.join(results_dir, "diagnostics")
    )
    
    # Create browser manager
    browser_manager = BrowserManager(
        visible=args.visible,
        diagnostics_manager=diagnostics_manager
    )
    
    try:
        # Initialize browser
        with diagnostics_manager.track_stage("browser_init"):
            await browser_manager.initialize()
            
            # Test URL (using Discord careers page)
            url = "https://job-boards.greenhouse.io/discord/jobs/7845336002"
            
            logger.info(f"Navigating to {url}")
            await browser_manager.goto(url)
            await browser_manager.wait_for_load()
        
        # Initialize LLM
        llm = initialize_llm()
        
        # Create form analyzer agent
        form_analyzer = FormAnalyzerAgent(llm=llm, verbose=args.verbose)
        
        # Analyze form
        with diagnostics_manager.track_stage("form_analysis"):
            logger.info("Analyzing form")
            
            # Get page HTML and analyze structure
            page_html = await browser_manager.get_page_html()
            form_structure = await form_analyzer.analyze_form_with_browser(browser_manager, url, args.visible)
            
            # Save form structure
            with open(os.path.join(results_dir, "form_structure.json"), "w") as f:
                json.dump(form_structure, f, indent=2)
        
        # Create user profile
        user_profile = create_test_profile()
        
        # Create profile adapter agent
        profile_adapter = ProfileAdapterAgent(llm=llm, verbose=args.verbose)
        
        # Map profile to form
        with diagnostics_manager.track_stage("profile_mapping"):
            logger.info("Mapping profile to form")
            
            # Map user profile to form fields
            profile_mapping = await profile_adapter.adapt_profile(
                user_profile=user_profile,
                form_structure=form_structure
            )
            
            # Save profile mapping
            with open(os.path.join(results_dir, "profile_mapping.json"), "w") as f:
                json.dump(profile_mapping, f, indent=2)
        
        # Execute form filling
        with diagnostics_manager.track_stage("form_execution"):
            logger.info("Executing form filling")
            
            # If requested to slow down for visibility
            if args.visible and args.slow:
                logger.info("Using slow execution mode for better visibility")
                
                # Create action executor with test_mode OFF to actually interact with the browser
                action_executor = ActionExecutor(browser_manager=browser_manager)
                action_executor.set_test_mode(False)  # Set to False to actually interact with the browser
                
                # Initialize application executor agent
                application_executor = ApplicationExecutorAgent(action_executor=action_executor)
                
                # Extract field mappings
                field_mappings = profile_mapping.get("field_mappings", [])
                field_results = []
                fields_filled = 0
                
                # Process each field manually with delays
                for field_mapping in field_mappings:
                    field_id = field_mapping.get("field_id")
                    value = field_mapping.get("value", "")
                    
                    # Skip empty fields or recaptcha
                    if not field_id or "recaptcha" in field_id.lower():
                        continue
                    
                    # Get field type 
                    field_type = application_executor._get_field_type(field_id, form_structure)
                    
                    # Ensure element is visible by scrolling to it
                    if hasattr(browser_manager, 'scroll_to_element'):
                        selector = f"#{field_id}"
                        # Use sanitized selector for fields with numeric IDs
                        if field_id.isdigit() or (field_id and field_id[0].isdigit()):
                            selector = f"[id='{field_id}']"
                            
                        await browser_manager.scroll_to_element(selector)
                        await asyncio.sleep(0.5)  # Pause after scrolling
                    
                    # Execute the field
                    result = await application_executor._execute_field(field_id, field_type, value, form_structure)
                    
                    if result.get("success", False):
                        fields_filled += 1
                        
                    field_results.append({
                        "field_id": field_id,
                        "field_type": field_type,
                        "success": result.get("success", False),
                        "value": value,
                        "error": result.get("error", "")
                    })
                    
                    # Add delay between actions
                    await asyncio.sleep(1.0)
                
                # Create execution results
                execution_results = {
                    "success": True,
                    "field_results": field_results,
                    "fields_filled": fields_filled
                }
            else:
                # Use the standard execute_form function
                execution_results = await execute_form(
                    form_structure=form_structure,
                    profile_mapping=profile_mapping,
                    browser_manager=browser_manager,
                    visible=args.visible,
                    test_mode=False  # Set to False to actually interact with the browser
                )
            
            # Save execution results
            with open(os.path.join(results_dir, "results.json"), "w") as f:
                json.dump(execution_results, f, indent=2)
        
        # Print results
        logger.info("Job application completed successfully (TEST MODE - No submission made)")
        logger.info(f"Results saved to {os.path.abspath(results_dir)}")
        
        # Print detailed results
        print_execution_results(execution_results)
        
        print(f"✅ Test completed successfully!")
        print(f"📊 Results saved to {os.path.abspath(results_dir)}")
        print(f"Fields filled: {execution_results.get('fields_filled', 0)}/{len(execution_results.get('field_results', []))}")
    
    except Exception as e:
        logger.error(f"Error in test: {str(e)}", exc_info=args.verbose)
        print(f"❌ Test failed: {str(e)}")
        return 1
    
    finally:
        # Close browser
        logger.info("Closing centralized BrowserManager.")
        with diagnostics_manager.track_stage("browser_close"):
            await browser_manager.close()
    
    return 0

def main():
    """Main entry point for testing Discord job application."""
    parser = argparse.ArgumentParser(description="Test Discord Job Application")
    parser.add_argument("--visible", action="store_true", help="Show browser during execution")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--slow", action="store_true", help="Slow down execution for visibility")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run the test
    exit_code = asyncio.run(test_discord_application(args))
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main() 