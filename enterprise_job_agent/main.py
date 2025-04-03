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

# LLM imports
# Import CrewAI's LLM class
from crewai import LLM

# Local imports
from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.job_extractor import extract_job_data
from enterprise_job_agent.core.profile_manager import ProfileManager
from enterprise_job_agent.core.crew_manager import JobApplicationCrew
from enterprise_job_agent.core.frame_manager import AdvancedFrameManager
from enterprise_job_agent.config import Config
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.core.action_executor import ActionExecutor
from enterprise_job_agent.agents.form_analyzer_agent import FormAnalyzerAgent
from enterprise_job_agent.agents.profile_adapter_agent import ProfileAdapterAgent
from enterprise_job_agent.agents.application_executor_agent import ApplicationExecutorAgent
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.tools.element_selector import ElementSelector

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('job_application.log')
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
    output_dir: Optional[str] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """Analyze and process a job application.
    
    Args:
        url: URL of the job application
        test_mode: Whether to run in test mode (don't submit)
        visible: Whether to show the browser
        user_profile_path: Path to the user profile JSON
        output_dir: Directory to save results
        verbose: Whether to enable verbose output
        
    Returns:
        Dict containing the results
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Generate a unique job ID
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    
    # Setup output directory
    if not output_dir:
        output_dir = Path(__file__).parent / "test_results" / job_id
    else:
        output_dir = Path(output_dir) / job_id
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup diagnostics
    diagnostics_manager = DiagnosticsManager()
    
    # Create and initialize browser manager
    browser_manager = BrowserManager(visible=visible, diagnostics_manager=diagnostics_manager)
    
    try:
        with diagnostics_manager.track_stage("initialization"):
            await browser_manager.initialize()
        
        # Initialize tools
        element_selector = ElementSelector(browser_manager, diagnostics_manager)
        form_interaction = FormInteraction(browser_manager, element_selector, diagnostics_manager)
        
        # Initialize action executor
        action_executor = ActionExecutor(
            browser_manager=browser_manager,
            element_selector=element_selector,
            form_interaction=form_interaction,
            diagnostics_manager=diagnostics_manager
        )
        
        # Load LLM
        # Use CrewAI's LLM class with Gemini model
        try:
            import os
            from crewai import LLM
            
            # Use environment variable for API key
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                logger.warning("No GEMINI_API_KEY found in environment variables. Some functionalities might be limited.")
            
            # Initialize LLM with CrewAI's LLM class
            llm = LLM(
                model="gemini/gemini-2.0-flash",
                api_key=api_key,
                temperature=0.2
            )
            
            # Test that the LLM works by calling a simple prompt
            logger.debug("Testing LLM with a simple prompt")
            try:
                test_result = llm.call("Say hello!")
                logger.debug(f"LLM test result: {test_result}")
            except Exception as e:
                logger.error(f"LLM test failed: {e}")
                raise ValueError(f"LLM initialization succeeded but test call failed: {e}")
                
        except ImportError as e:
            logger.error(f"Failed to import required LLM libraries: {e}")
            raise
        
        # Initialize agents
        form_analyzer_agent = FormAnalyzerAgent(llm=llm, verbose=verbose)
        profile_adapter_agent = ProfileAdapterAgent(llm=llm, verbose=verbose)
        application_executor_agent = ApplicationExecutorAgent(
            llm=llm,
            action_executor=action_executor,
            diagnostics_manager=diagnostics_manager,
            verbose=verbose
        )
        
        # Load user profile
        if user_profile_path:
            with open(user_profile_path, "r") as f:
                user_profile = json.load(f)
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
        
        # Navigate to the job URL
        with diagnostics_manager.track_stage("navigation"):
            logger.info(f"Navigating to {url}")
            await browser_manager.goto(url)
            await browser_manager.wait_for_load()
        
        # Extract form data from page
        with diagnostics_manager.track_stage("form_extraction"):
            logger.info("Extracting form data")
            
            # Get page HTML for enhanced form analysis
            page_html = await browser_manager.get_page_html()
            
            # Use enhanced form analyzer to analyze HTML structure
            form_structure = form_analyzer_agent.analyze_form_html(page_html, url)
            
            # Take a screenshot of the form
            form_screenshot_path = output_dir / "initial_form.png"
            await browser_manager.take_screenshot(str(form_screenshot_path))
            
            # Log structure
            logger.debug(f"Form structure: {json.dumps(form_structure, indent=2)}")
            
            # Store form structure for debugging
            with open(output_dir / "form_structure.json", "w") as f:
                json.dump(form_structure, f, indent=2)
        
        # Generate a mapping from user profile to form fields
        with diagnostics_manager.track_stage("profile_mapping"):
            logger.info("Mapping user profile to form fields")
            profile_mapping = await profile_adapter_agent.map_profile_to_form(user_profile, form_structure)
            
            # Store mapping for debugging
            with open(output_dir / "profile_mapping.json", "w") as f:
                json.dump(profile_mapping, f, indent=2)
        
        # Execute form filling
        with diagnostics_manager.track_stage("form_execution"):
            logger.info("Executing form filling")
            execution_results = await application_executor_agent.execute_plan(profile_mapping, form_structure)
            
            # Store results for debugging
            with open(output_dir / "execution_results.json", "w") as f:
                json.dump(execution_results, f, indent=2)
            
            # Take final screenshot
            final_screenshot_path = output_dir / "final_form.png"
            await browser_manager.take_screenshot(str(final_screenshot_path))
        
        # Generate summary and store results
        with open(output_dir / "results.json", "w") as f:
            results = {
                "job_id": job_id,
                "url": url,
                "test_mode": test_mode,
                "execution_results": execution_results,
                "diagnostics": diagnostics_manager.get_diagnostics()
            }
            json.dump(results, f, indent=2)
        
        logger.info(f"Job application completed successfully ({'TEST MODE - No submission made' if test_mode else 'SUBMITTED'})")
        logger.info(f"Results saved to {output_dir / 'results.json'}")
        
        # Print detailed field execution results
        field_results = execution_results.get("field_results", [])
        fields_filled = execution_results.get("fields_filled", 0)
        fields_failed = execution_results.get("fields_failed", 0)
        field_type_stats = execution_results.get("field_type_stats", {})
        
        print("\n===== FIELD EXECUTION RESULTS =====")
        print(f"Fields filled: {fields_filled}")
        print(f"Fields failed: {fields_failed}")
        print()
        
        # Print field type statistics
        print("Field Type Statistics:")
        for field_type, stats in field_type_stats.items():
            success_rate = (stats["success"] / stats["total"]) * 100
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
        
        return results
        
    except Exception as e:
        logger.error(f"Error in job application process: {str(e)}")
        
        # Save error information
        with open(output_dir / "error.json", "w") as f:
            error_info = {
                "error": str(e),
                "diagnostics": diagnostics_manager.get_diagnostics() if diagnostics_manager else {}
            }
            json.dump(error_info, f, indent=2)
        
        # Take error screenshot if browser is available
        try:
            error_screenshot_path = output_dir / "error.png"
            await browser_manager.take_screenshot(str(error_screenshot_path))
        except:
            pass
        
        return {
            "success": False,
            "error": str(e),
            "job_id": job_id
        }
    
    finally:
        logger.info("Closing centralized BrowserManager.")
        await browser_manager.close()

def main():
    """Main entry point for the job application agent."""
    parser = argparse.ArgumentParser(description="Enterprise Job Application Agent")
    parser.add_argument("action", choices=["apply", "analyze", "test"], help="Action to perform")
    parser.add_argument("--url", required=True, help="URL of the job application")
    parser.add_argument("--profile", help="Path to user profile JSON")
    parser.add_argument("--output", help="Output directory for results")
    parser.add_argument("--visible", action="store_true", help="Show the browser during execution")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Run the job application process
    test_mode = args.action in ["test", "analyze"]
    
    try:
        results = asyncio.run(
            analyze_job_application(
                url=args.url,
                test_mode=test_mode,
                visible=args.visible,
                user_profile_path=args.profile,
                output_dir=args.output,
                verbose=args.verbose
            )
        )
        
        if results.get("success", False) is False and "error" in results:
            logger.error(f"Job application failed: {results['error']}")
            sys.exit(1)
        else:
            logger.info(f"Test completed successfully. Results saved to {args.output}")
            
    except Exception as e:
        logger.error(f"Error running job application: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 