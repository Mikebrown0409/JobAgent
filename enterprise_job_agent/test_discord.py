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
import pytest # Add import for pytest

# Add parent directory to path to import enterprise_job_agent modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.agents.form_analyzer_agent import FormAnalyzerAgent
from enterprise_job_agent.agents.profile_adapter_agent import ProfileAdapterAgent
from enterprise_job_agent.core.action_executor import ActionExecutor
from enterprise_job_agent.core.action_executor import ActionContext
from enterprise_job_agent.tools.element_selector import ElementSelector
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.main import execute_form

# Import CrewAI LLM
from crewai import LLM

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
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

# Load user profile from test_user
def load_user_profile():
    """Load the detailed user profile from test_user directory."""
    # Path to user profile JSON
    profile_path = os.path.join(os.path.dirname(__file__), "test_user", "user_profile.json")
    
    # Check if file exists
    if not os.path.exists(profile_path):
        logger.error(f"User profile not found at {profile_path}")
        sys.exit(1)
    
    # Load the JSON profile
    with open(profile_path, 'r') as f:
        user_data = json.load(f)
    
    # Base directory for test files
    test_user_dir = os.path.join(os.path.dirname(__file__), "test_user")
    
    # Create a standardized profile structure
    return {
        "personal_info": {
            "first_name": user_data["personal"]["first_name"],
            "last_name": user_data["personal"]["last_name"],
            "email": user_data["personal"]["email"],
            "phone": user_data["personal"]["phone"],
            "linkedin": user_data["personal"].get("linkedin", ""),
            "location": {
                "city": user_data["location"]["city"],
                "state": user_data["location"]["state"],
                "country": user_data["location"]["country"]
            }
        },
        "resume_path": os.path.join(test_user_dir, user_data["documents"]["resume"]) if user_data["documents"]["resume"] else "",
        "cover_letter_path": os.path.join(test_user_dir, user_data["documents"].get("cover_letter", "")),
        "education": [
            {
                "school": edu["school"],
                "degree": edu["degree"],
                "field_of_study": edu["discipline"],
                "graduation_year": edu["grad_year"]
            } for edu in user_data["education"]
        ],
        "diversity": {
            "gender": user_data["diversity"]["gender"],
            "race": user_data["diversity"]["race"],
            "hispanic": user_data["diversity"]["hispanic"],
            "veteran": user_data["diversity"]["veteran"],
            "disability": user_data["diversity"]["disability"]
        },
        "preferences": {
            "work_authorization": user_data["preferences"]["work_authorization"],
            "commute_willingness": user_data["preferences"]["commute_willingness"]
        },
        "custom_questions": user_data["custom_questions"]
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
@pytest.mark.asyncio # Add the pytest-asyncio decorator
async def test_discord_application():
    """Test Discord job application process."""
    # --- Hardcoded Config for Pytest --- 
    visible = True # Run with visible browser to watch the form filling
    verbose = True # Enable verbose logging for tests
    slow = True # Run in slow mode for better visibility
    delay = 0.5 # Longer delay to see each field being filled
    # ---

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
        visible=visible,
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
        form_analyzer = FormAnalyzerAgent(llm=llm, verbose=verbose)
        
        # Analyze form
        with diagnostics_manager.track_stage("form_analysis"):
            logger.info("Analyzing form")
            
            # Get page HTML and analyze structure
            page_html = await browser_manager.get_page_html()
            
            # Create a dictionary with just the main frame for analysis
            main_frame = browser_manager.page.main_frame
            frames_dict = {"main": main_frame}
            
            form_structure = await form_analyzer.analyze_form_with_browser(browser_manager, url, frames_dict)
            
            # Save form structure
            with open(os.path.join(results_dir, "form_structure.json"), "w") as f:
                json.dump(form_structure, f, indent=2)
        
        # Load comprehensive user profile from test_user directory
        user_profile = load_user_profile()
        
        # Create profile adapter agent
        profile_adapter = ProfileAdapterAgent(llm=llm, verbose=verbose)
        
        # Map profile to form
        with diagnostics_manager.track_stage("profile_mapping"):
            logger.info("Mapping profile to form")
            
            # Map user profile to form fields
            profile_mapping = await profile_adapter.adapt_profile(
                user_profile=user_profile,
                form_elements=form_structure
            )
            
            # Save profile mapping
            with open(os.path.join(results_dir, "profile_mapping.json"), "w") as f:
                json.dump([action.__dict__ for action in profile_mapping], f, indent=2)
        
        # Execute form filling
        with diagnostics_manager.track_stage("form_execution"):
            logger.info("Executing form filling")
            
            # If requested to slow down for visibility
            if visible and slow:
                logger.info("Using slow execution mode for better visibility")
                
                # Create form interaction and element selector with browser manager
                element_selector = ElementSelector(browser_manager, diagnostics_manager)
                form_interaction = FormInteraction(browser_manager, element_selector, diagnostics_manager)
                
                # Create action executor with test_mode OFF to actually interact with the browser
                action_executor = ActionExecutor(
                    browser_manager=browser_manager, 
                    diagnostics_manager=diagnostics_manager,
                    form_interaction=form_interaction,
                    element_selector=element_selector
                )
                action_executor.set_test_mode(False)  # Set to False to actually interact with the browser
                
                # The profile_mapping is already a list of ActionContext objects
                field_results = []
                fields_filled = 0
                fields_failed = 0 # Initialize failed count
                field_type_stats = {} # Initialize stats
                
                # Process each action context with delays
                for action_context in profile_mapping:
                    field_id = action_context.field_id
                    field_type = action_context.field_type
                    value = action_context.field_value
                    frame_id = action_context.frame_id
                    fallback_text = action_context.fallback_text
                    
                    # Format the field_id as a CSS selector if it isn't already
                    if field_id and not field_id.startswith(('#', '.')):
                        field_id = f"#{field_id}"
                        # Update the action_context with the new field_id
                        action_context.field_id = field_id
                    
                    # Check if this is a typeahead field (for better handling)
                    if field_type == "select" or field_type == "dropdown":
                        # Convert select/dropdown fields to typeahead for education/location fields
                        is_typeahead = any(keyword in str(field_id).lower() for keyword in [
                            "school", "degree", "discipline", "location", "university",
                            "education", "city", "state", "country"
                        ])
                        if is_typeahead:
                            logger.info(f"Converting field '{field_id}' from '{field_type}' to 'typeahead' for better handling")
                            field_type = "typeahead"
                            action_context.field_type = "typeahead"
                    
                    # Skip empty fields or recaptcha
                    if (not field_id and field_type != "click") or "recaptcha" in str(field_id).lower():
                        logger.debug(f"Skipping field: {field_id or fallback_text} (Type: {field_type})")
                        continue

                    # Update stats count for this type
                    if field_type not in field_type_stats:
                        field_type_stats[field_type] = {"total": 0, "success": 0}
                    field_type_stats[field_type]["total"] += 1
                        
                    logger.info(f"Processing field: {field_id or fallback_text} (Type: {field_type}) with value: {str(value)[:50]}...")
                    
                    # Execute the action using ActionExecutor
                    try:
                        success = await action_executor.execute_action(action_context)
                        field_result = {
                            "field_id": field_id or fallback_text,
                            "field_type": field_type,
                            "value": value,
                            "success": success,
                            "error": None
                        }
                        if success:
                            fields_filled += 1
                            field_type_stats[field_type]["success"] += 1
                        else:
                            fields_failed += 1
                            field_result["error"] = f"ActionExecutor failed for {field_type}" # Basic error
                            logger.warning(f"Failed to process field {field_id or fallback_text} (Type: {field_type})")
                    except Exception as e:
                        success = False
                        fields_failed += 1
                        field_result = {
                            "field_id": field_id or fallback_text,
                            "field_type": field_type,
                            "value": value,
                            "success": False,
                            "error": str(e)
                        }
                        logger.error(f"Error processing field {field_id or fallback_text} (Type: {field_type}): {e}", exc_info=True)
                    
                    field_results.append(field_result)
                    
                    # Wait for a short period after each action
                    await asyncio.sleep(delay)
                
                # Prepare final results for slow mode
                execution_results = {
                    "fields_filled": fields_filled,
                    "fields_failed": fields_failed,
                    "field_results": field_results,
                    "field_type_stats": field_type_stats
                }
                
                # Print and save results
                print_execution_results(execution_results)
                
                # Save results to file
                with open(os.path.join(results_dir, "execution_results.json"), "w") as f:
                    json.dump(execution_results, f, indent=2)
                    
                return execution_results
            
            # Normal execution without extra delays
            execution_results = await execute_form(
                browser_manager=browser_manager,
                profile_mapping=profile_mapping,
                form_structure=form_structure,
                test_mode=True,  # Set to True to prevent actual form submission
                # Add missing arguments
                llm=llm,
                verbose=verbose,
                output_dir=results_dir
                # Assuming execute_form might eventually use verbose setting
                # verbose=verbose 
            )
            
            # Print and save results
            print_execution_results(execution_results)
            
            # Save results to file
            with open(os.path.join(results_dir, "execution_results.json"), "w") as f:
                json.dump(execution_results, f, indent=2)
                
            return execution_results
    
    except Exception as e:
        logger.error(f"Error in test: {str(e)}")
        raise
    
    finally:
        # Close browser
        with diagnostics_manager.track_stage("browser_close"):
            await browser_manager.close()

if __name__ == "__main__":
    """Entry point for direct script execution."""
    import asyncio
    
    print("Starting Discord test execution...")
    # Run the test async function directly
    result = asyncio.run(test_discord_application())
    
    # Print results
    if result:
        print("\n===== TEST EXECUTION COMPLETE =====")
        print_execution_results(result)
    else:
        print("\n===== TEST EXECUTION FAILED =====")
    
    print("Test completed.")

