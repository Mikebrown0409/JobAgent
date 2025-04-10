"""Main module for the enterprise job application system."""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import difflib
from typing import Dict, Any, Optional, List
import re
import uuid
from datetime import datetime
from pathlib import Path
import traceback
import yaml  # Add YAML support

# LLM imports
# Import CrewAI's LLM class
from crewai import LLM

# Local imports
from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.job_extractor import extract_job_data
from enterprise_job_agent.core.crew_manager import JobApplicationCrew
from enterprise_job_agent.core.frame_manager import AdvancedFrameManager
from enterprise_job_agent.config import Config
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.core.action_executor import ActionExecutor
from enterprise_job_agent.agents.form_analyzer_agent import FormAnalyzerAgent
from enterprise_job_agent.agents.profile_adapter_agent import ProfileAdapterAgent
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.tools.element_selector import ElementSelector
from enterprise_job_agent.agents.error_recovery_agent import ErrorRecoveryAgent
from enterprise_job_agent.core.action_strategy_selector import ActionStrategySelector

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        # logging.FileHandler('job_application.log') # Maybe disable this if logs go to run dir
    ]
)

logger = logging.getLogger(__name__)

def initialize_llm(model_name: str = "gemini-2.0-flash", **kwargs):
    """Initializes the LLM using CrewAI's LLM class directly.
    
    Returns a configured CrewAI LLM instance.
    """
    # Ensure the model name has the provider prefix
    if not model_name.startswith("gemini/"):
        model_name = f"gemini/{model_name}"
        
    logger.info(f"Initializing CrewAI LLM with model: {model_name}")
    
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        logger.error("GEMINI_API_KEY not found in environment. Cannot initialize LLM.")
        raise ValueError("GEMINI_API_KEY is required but not found.")

    try:
        # Create and return a CrewAI LLM instance
        llm = LLM(
            model=model_name,
            api_key=gemini_api_key,
            **kwargs
        )
            
        logger.info("CrewAI LLM initialized successfully.")
        return llm
    except Exception as e:
        # Use a more specific error message if possible
        logger.error(f"Failed to initialize CrewAI LLM: {e}", exc_info=True)
        raise

# Remove OpenAI and TogetherAI blocks
# elif use_openai:
#    ...
# elif use_together:
#    ...
# else:
#    ...

# Remove unused parameters from run_job_application
async def analyze_job_application(
    url: str,
    test_mode: bool = True,
    visible: bool = False,
    user_profile_path: Optional[str] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """Analyze and process a job application.
    
    Args:
        url: URL of the job application
        test_mode: Whether to run in test mode (don't submit)
        visible: Whether to show the browser
        user_profile_path: Path to the user profile JSON or YAML
        verbose: Whether to enable verbose output
        
    Returns:
        Dict containing the results
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Generate a unique run ID based on timestamp
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Setup diagnostics with the run ID
    diagnostics_manager = DiagnosticsManager(run_id=run_id)
    
    # Optional: Add file handler for logging to the run directory
    log_file_path = os.path.join(diagnostics_manager.run_output_dir, 'run.log')
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(file_handler)

    logger.info(f"Starting job application analysis for URL: {url}, Run ID: {run_id}")
    
    # Create and initialize browser manager
    browser_manager = BrowserManager(visible=visible, diagnostics_manager=diagnostics_manager)
    
    try:
        with diagnostics_manager.track_stage("initialization"):
            await browser_manager.initialize()
            
            # --- Navigate to the URL AFTER browser initialization --- 
            logger.info(f"Navigating to target URL: {url}")
            await browser_manager.navigate(url) # Use BrowserManager's navigate
            await browser_manager.wait_for_load() # Wait for page to settle
            logger.info("Navigation complete.")
            # --- End Navigation ---
            
            # Initialize LLM
            llm = initialize_llm() # Call the separate function
            
            # Initialize tools
            element_selector = ElementSelector(browser_manager, diagnostics_manager)
            form_interaction = FormInteraction(browser_manager, element_selector, diagnostics_manager)
            
            # Instantiate ActionStrategySelector
            strategy_selector = ActionStrategySelector(llm=llm, diagnostics_manager=diagnostics_manager)
            
            # Initialize action executor AFTER LLM and strategy selector are initialized
            action_executor = ActionExecutor(
                browser_manager=browser_manager,
                form_interaction=form_interaction,
                element_selector=element_selector,
                diagnostics_manager=diagnostics_manager,
                strategy_selector=strategy_selector,
                llm=llm
            )
            
            # Initialize agents
            form_analyzer_agent = FormAnalyzerAgent(llm=llm, verbose=verbose)
            profile_adapter_agent = ProfileAdapterAgent(llm=llm, verbose=verbose)
            error_recovery_agent = ErrorRecoveryAgent.create(llm=llm, verbose=verbose)

            # Load user profile
            if user_profile_path:
                with open(user_profile_path, "r") as f:
                    # Detect file format based on extension
                    if user_profile_path.endswith('.yaml') or user_profile_path.endswith('.yml'):
                        user_profile = yaml.safe_load(f)
                    else:
                        try:
                            user_profile = json.load(f)
                        except json.JSONDecodeError:
                            # Fallback to YAML if JSON parsing fails
                            f.seek(0)  # Reset file pointer to beginning
                            user_profile = yaml.safe_load(f)
            else:
                # Use a sample profile for testing
                user_profile = {
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
                    "education": [
                        {
                            "school": "University of California, Berkeley",
                            "degree": "Bachelor of Science",
                            "field_of_study": "Computer Science",
                            "graduation_date": "2021-05-15"
                        }
                    ],
                    "work_experience": [
                        {
                            "company": "Tech Innovations Inc.",
                            "title": "Software Engineer",
                            "location": "San Francisco, CA",
                            "start_date": "2021-06-01",
                            "end_date": None,
                            "is_current": True,
                            "description": "Developing cloud-based solutions using modern frameworks"
                        },
                        {
                            "company": "StartUp Labs",
                            "title": "Software Engineering Intern",
                            "location": "Palo Alto, CA",
                            "start_date": "2020-05-01",
                            "end_date": "2020-08-31",
                            "is_current": False,
                            "description": "Worked on front-end development using React"
                        }
                    ],
                    "skills": [
                        "JavaScript", "React", "Node.js", "Python", "Java", "Docker", "AWS"
                    ],
                    "languages": [
                        {
                            "language": "English",
                            "proficiency": "Native"
                        },
                        {
                            "language": "Mandarin",
                            "proficiency": "Fluent"
                        }
                    ],
                    "preferences": {
                        "willing_to_relocate": True,
                        "work_authorization": "US Citizen",
                        "desired_salary": "Competitive",
                        "desired_job_type": "Full-time"
                    },
                    "demographic_info": {
                        "gender": "Male",
                        "race": "White",
                        "hispanic_ethnicity": "No",
                        "disability_status": "No",
                        "veteran_status": "No"
                    },
                    "projects": [
                        {
                            "title": "Community Marketplace",
                            "description": "Built a full-stack marketplace application",
                            "url": "https://github.com/alexchen/marketplace"
                        }
                    ],
                    "certifications": [
                        {
                            "name": "AWS Certified Developer",
                            "issuer": "Amazon Web Services",
                            "date": "2022-03-01"
                        }
                    ],
                    "links": {
                        "linkedin": "https://linkedin.com/in/alexchen",
                        "github": "https://github.com/alexchen",
                        "portfolio": None
                    }
                }
                logger.warning("No user profile provided, using sample profile.")
            
        # Initialize Crew Manager
        with diagnostics_manager.track_stage("crew_initialization"):
            crew_manager = JobApplicationCrew(
                url=url,
                user_profile=user_profile,
                browser_manager=browser_manager,
                action_executor=action_executor,
                form_analyzer_agent=form_analyzer_agent,
                profile_adapter_agent=profile_adapter_agent,
                error_recovery_agent=error_recovery_agent, # Pass the recovery agent
                diagnostics_manager=diagnostics_manager,
                test_mode=test_mode,
            )

        # Kick off the job application process
        results = await crew_manager.run()

        # Save final diagnostics (stages, overall result) if needed, 
        # though intermediate results are the primary goal here.
        # diagnostics_manager.save_final_report() # Example - if we add such a method
        
        logger.info(f"Job application processing finished for Run ID: {run_id}. Results: {results}")
        return results

    except Exception as e:
        error_msg = f"An unexpected error occurred during job application processing for Run ID {run_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        diagnostics_manager.error(error_msg) # Log error via diagnostics
        # Ensure the current stage is marked as failed if an exception bubbles up
        if diagnostics_manager.current_stage:
             diagnostics_manager.end_stage(success=False, error=f"Unhandled exception: {str(e)}")
        return {"status": "error", "message": error_msg, "run_id": run_id, "traceback": traceback.format_exc()}
    
    finally:
        logger.info(f"Cleaning up browser for Run ID: {run_id}")
        await browser_manager.close()
        # Remove the file handler specific to this run
        logging.getLogger().removeHandler(file_handler)

async def execute_form(
    form_structure: Dict[str, Any],
    profile_mapping: Dict[str, Any],
    browser_manager: BrowserManager,
    llm: Any, 
    verbose: bool,
    output_dir: Path,
    test_mode: bool = True
) -> Dict[str, Any]:
    """Execute form filling based on the form structure and profile mapping.
    
    Args:
        form_structure: Analyzed form structure
        profile_mapping: Profile to form field mapping (actually the pre-generated action plan)
        browser_manager: Browser manager instance
        llm: Language model instance
        verbose: Verbosity flag
        output_dir: Directory to save results
        test_mode: Whether to run in test mode without submitting
        
    Returns:
        Dictionary with execution results
    """
    logger.info("Executing form using helper function")
    
    # Initialize tools and executor (as done in analyze_job_application)
    diagnostics_manager = DiagnosticsManager() # Or get from browser_manager if shared
    element_selector = ElementSelector(browser_manager, diagnostics_manager)
    form_interaction = FormInteraction(browser_manager, element_selector, diagnostics_manager)
    # Instantiate ActionStrategySelector within this function's scope
    strategy_selector = ActionStrategySelector(llm=llm, diagnostics_manager=diagnostics_manager) 
    action_executor = ActionExecutor(
        browser_manager=browser_manager, 
        form_interaction=form_interaction,
        element_selector=element_selector,
        diagnostics_manager=diagnostics_manager,
        strategy_selector=strategy_selector,
        llm=llm
    )
    action_executor.set_test_mode(not test_mode) # Set based on test_mode flag

    # Assume profile_mapping already contains the list of ActionContext objects
    action_plan = profile_mapping # Rename for clarity
    if not isinstance(action_plan, list): 
        logger.error(f"execute_form expected a list of actions (ActionContext) but got {type(action_plan)}. Regenerating plan.")
        # Need to regenerate the plan if it wasn't passed correctly
        profile_adapter = ProfileAdapterAgent(llm=llm, verbose=verbose)
        # Need user_profile here - how to get it?
        # Let's assume it needs to be passed in or loaded
        # For now, raise error or return empty results
        logger.error("Cannot regenerate action plan within execute_form without user_profile.")
        return {"error": "Invalid action plan received and cannot regenerate."} 

    logger.info(f"Executing action plan with {len(action_plan)} actions.")
    # Execute the plan (list of actions)
    results = await action_executor.execute_form_actions(
        actions=action_plan,
        stop_on_error=False # Continue on error in test mode? Maybe make configurable
    )
    
    # Format results similar to analyze_job_application
    # This part needs careful implementation based on what execute_form_actions returns
    # Assuming it returns a dict like: {action_key: (success, error_message)}
    formatted_results = {
        "fields_filled": sum(1 for success, _ in results.values() if success),
        "fields_failed": sum(1 for success, _ in results.values() if not success),
        "field_results": [
            {
             "field_id": key.split('_')[1] if len(key.split('_')) > 1 else key, # Attempt to extract ID
             "field_type": key.split('_')[0] if len(key.split('_')) > 0 else "unknown", # Attempt to extract type
             "success": success,
             "error": error
            } for key, (success, error) in results.items()
        ],
        # field_type_stats needs more complex aggregation based on field_results
        "field_type_stats": {}
    }

    # Aggregate field_type_stats
    stats = {}
    for res in formatted_results["field_results"]:
        f_type = res["field_type"]
        if f_type not in stats:
            stats[f_type] = {"total": 0, "success": 0}
        stats[f_type]["total"] += 1
        if res["success"]:
            stats[f_type]["success"] += 1
    formatted_results["field_type_stats"] = stats

    return formatted_results

def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="Automate job applications.")
    parser.add_argument("url", help="URL of the job application page.")
    parser.add_argument("-p", "--profile", help="Path to the user profile JSON or YAML file.")
    parser.add_argument("--test", action="store_true", default=True, help="Run in test mode (don't submit). Default is True.")
    parser.add_argument("--no-test", dest="test", action="store_false", help="Run in live mode (attempt submission).")
    parser.add_argument("--visible", action="store_true", help="Show the browser window.")
    # parser.add_argument("--output-dir", help="Directory to save run results.") # Removed
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging.")

    args = parser.parse_args()

    try:
        asyncio.run(analyze_job_application(
            url=args.url,
            test_mode=args.test,
            visible=args.visible,
            user_profile_path=args.profile,
            # output_dir=args.output_dir, # Removed
            verbose=args.verbose
        ))
    except Exception as e:
        logger.critical(f"Application failed with unhandled exception: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main() 