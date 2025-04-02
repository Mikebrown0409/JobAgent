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
        # Initialize CrewAI's LLM class directly with the provider/model_name format
        llm = LLM(
            model=model_name,
            api_key=gemini_api_key,
            **kwargs
        )
            
        logger.info("CrewAI LLM instance initialized successfully.")
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
async def run_job_application(
    job_url: str,
    test_mode: bool,
    verbose: bool,
    visible: bool,
    output_dir: str,
    config: Config,
) -> Dict[str, Any]:
    """
    Run the job application process using the Gemini AI Agent.
    
    Args:
        job_url: URL of the job posting
        test_mode: Whether to run in test mode (no actual submission)
        verbose: Whether to enable verbose logging
        visible: Whether to run the browser in visible mode
        output_dir: Directory to save test results
        config: Configuration object
        
    Returns:
        Results of the job application process
    """
    logger.info(f"Starting job application process for {job_url}")
    if test_mode:
        logger.info("RUNNING IN TEST MODE - No job application will be submitted")
    
    browser_manager = None
    results_dir = None  # Initialize results_dir here
    job_id = str(uuid.uuid4())[:8] # Define job_id early for error reporting
    logger.info(f"Job application ID: {job_id}")

    try:
        logger.info("Initializing Gemini LLM for CrewAI")
        llm = initialize_llm()
        logger.info("LLM initialized.")

        # Construct profile path from config
        profiles_dir = os.path.expanduser(config.get('profiles.profiles_dir', '~/.jobagent/profiles'))
        default_profile_name = config.get('profiles.default_profile', 'default')
        profile_path = os.path.join(profiles_dir, f"{default_profile_name}.json")
        logger.info(f"Loading user profile from: {profile_path}")
        profile_manager = ProfileManager(profile_path)
        user_profile = profile_manager.get_profile()
        
        # Create output directory for results - moved here after potential profile errors
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Use the output_dir argument passed to the function
        base_output_dir = os.path.join(script_dir, output_dir) 
        results_dir = os.path.join(base_output_dir, f"job_{job_id}")
        os.makedirs(results_dir, exist_ok=True)
        logger.info(f"Created results directory: {results_dir}")
        
        # --- Centralized Browser Manager Initialization --- 
        frame_manager = None
        try:
            # Instantiate managers
            # Frame manager needs page, so start browser first
            temp_bm_for_startup = BrowserManager(headless=not visible)
            if not await temp_bm_for_startup.start():
                 logger.error("Failed to start browser during initial setup")
                 return {"success": False, "error": "Browser startup failed"}
                 
            page = await temp_bm_for_startup.get_page()
            frame_manager = AdvancedFrameManager(page)
            # Create the main browser manager, passing the frame manager
            browser_manager = BrowserManager(headless=not visible, frame_manager=frame_manager)
            # Assign the already started components from temp manager
            browser_manager.playwright = temp_bm_for_startup.playwright
            browser_manager.browser = temp_bm_for_startup.browser
            browser_manager.context = temp_bm_for_startup.context
            browser_manager.page = temp_bm_for_startup.page
            # We don't need the temp manager anymore
            del temp_bm_for_startup
            
            logger.info("BrowserManager and AdvancedFrameManager initialized.")
            # --- End Centralized Browser Manager Initialization --- 

            # Extract job data using the centralized browser manager
            logger.info(f"Extracting job data from {job_url}")
            job_data = await extract_job_data(job_url, browser_manager)
            
            if not job_data:
                logger.error("Failed to extract job data")
                return {"success": False, "error": "Failed to extract job data"}
            
            # Save extracted form data for debugging
            job_data_file = f"{results_dir}/job_data.json"
            with open(job_data_file, "w") as f:
                json.dump(job_data, f, indent=2)
            logger.info(f"Job data saved to {job_data_file}")
            
            # Save screenshot to the results directory
            if "screenshot_path" in job_data and job_data["screenshot_path"]:
                try:
                    new_screenshot_path = f"{results_dir}/job_posting.png"
                    os.rename(job_data["screenshot_path"], new_screenshot_path)
                    job_data["screenshot_path"] = new_screenshot_path
                    logger.info(f"Screenshot saved to {new_screenshot_path}")
                except Exception as e:
                    logger.warning(f"Failed to move screenshot: {e}")
            
            # Initialize job application crew, passing the browser manager
            logger.info("Initializing job application crew")
            crew_manager = JobApplicationCrew(
                llm=llm,
                browser_manager=browser_manager, # Pass the manager
                verbose=verbose
            )
            
            # Execute job application process
            logger.info(f"Executing job application process {'(TEST MODE)' if test_mode else ''}")
            result = await crew_manager.execute_job_application_process(
                form_data=job_data["form_structure"],
                user_profile=user_profile,
                job_description=job_data["job_details"],
                test_mode=test_mode,
                job_url=job_url
            )
            
            # Save results
            result_file = f"{results_dir}/results.json"
            with open(result_file, "w") as f:
                json.dump(result, f, indent=2)
            
            # Take a final screenshot in test mode
            if test_mode and browser_manager:
                try:
                    screenshot_path = f"{results_dir}/final_form.png"
                    await browser_manager.take_screenshot(screenshot_path)
                    logger.info(f"Final form screenshot saved to {screenshot_path}")
                    result["test_mode_screenshot"] = screenshot_path
                except Exception as screenshot_error:
                    logger.warning(f"Failed to take final screenshot: {screenshot_error}")
            
            success_state = "completed successfully" if result["success"] else "failed"
            test_mode_indicator = " (TEST MODE - No submission made)" if test_mode else ""
            logger.info(f"Job application {success_state}{test_mode_indicator}")
            logger.info(f"Results saved to {result_file}")
            
            # Add test mode information to result
            if test_mode:
                result["test_mode"] = True
                result["test_mode_info"] = "This was a test run. No actual job application was submitted."
            
            # Add results directory to the result
            result["results_dir"] = results_dir
            result["report_file"] = result_file
            
            return result
        except Exception as e:
            logger.error(f"Error during browser/crew phase: {str(e)}", exc_info=True)
            # Save error information (check if results_dir exists)
            if results_dir:
                error_file = os.path.join(results_dir, "error.json") # Use os.path.join
                try:
                    with open(error_file, "w", encoding='utf-8') as f: # Add encoding
                        json.dump({
                            "error": str(e),
                            "job_id": job_id,
                            "stage": "browser/crew",
                            "test_mode": test_mode,
                            "timestamp": datetime.now().isoformat()
                        }, f, indent=2)
                    logger.info(f"Error details saved to {error_file}")
                except Exception as write_error:
                    logger.warning(f"Failed to save error details: {write_error}")
            
            # Return error structure
            return {
                "success": False, 
                "error": str(e), 
                "job_id": job_id, 
                "test_mode": test_mode,
                "results_dir": results_dir # Can be None if error occurred early
            }
            
    except Exception as initial_error: # Catch errors during init (LLM, profile, results_dir)
        logger.error(f"Error during initialization phase: {str(initial_error)}", exc_info=True)
        
        # Attempt to save error information (check if results_dir exists)
        # Note: results_dir might still be None here if the error was before its creation
        if results_dir: 
            error_file = os.path.join(results_dir, "error.json") # Use os.path.join
            try:
                with open(error_file, "w", encoding='utf-8') as f: # Add encoding
                    json.dump({
                        "error": str(initial_error),
                        "job_id": job_id,
                        "stage": "initialization",
                        "test_mode": test_mode,
                        "timestamp": datetime.now().isoformat()
                    }, f, indent=2)
                logger.info(f"Initialization error details saved to {error_file}")
            except Exception as write_error:
                logger.warning(f"Failed to save initialization error details: {write_error}")
        else:
             logger.warning("results_dir not created, cannot save initialization error details to file.")
        
        # Return error structure
        return {
            "success": False, 
            "error": str(initial_error), 
            "job_id": job_id, 
            "test_mode": test_mode,
            "results_dir": results_dir # Will be None here
        }
    finally:
        # Close browser_manager if it was created
        if browser_manager:
            logger.info("Closing centralized BrowserManager.")
            await browser_manager.close()

def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(description="Enterprise Job Application Agent")
    
    parser.add_argument(
        "--job-url", 
        type=str, 
        required=True,
        help="URL of the job posting"
    )
        
    # Remove profile argument if handled by config
    # parser.add_argument(
    #     "--profile", 
    #     type=str, 
    #     help="Path to user profile JSON (default: uses config)"
    # )
        
    parser.add_argument(
        "--visible", 
        action="store_true", 
        help="Run with visible browser (default: headless)"
    )
    
    parser.add_argument(
        "--test", 
        action="store_true", 
        help="Run in test mode - no actual submission will be made"
    )
    
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="Enable verbose logging"
    )

    parser.add_argument(
        '--output-dir', 
        default='enterprise_job_agent/test_results', 
        help='Directory to save test results'
    )
    
    args = parser.parse_args()
    
    if args.test:
        print("🧪 RUNNING IN TEST MODE - No actual job application will be submitted")
        logger.info("Test mode enabled - application will not be submitted")
    
    print(f"⏳ Processing job application for URL: {args.job_url}")
    if args.visible:
        print("🔍 Browser will be visible during execution")

    # Load configuration
    config = Config()

    # API Key check is now implicitly handled by initialize_llm() raising an error
        
    try:
        # Call run_job_application without google_api_key
        result = asyncio.run(run_job_application(
            job_url=args.job_url, 
            test_mode=args.test, 
            verbose=args.verbose, 
            visible=args.visible,
            output_dir=args.output_dir,
            config=config,
            # google_api_key=args.google_api_key # Removed
        ))
        
        if result["success"]:
            if args.test:
                print("✅ Test run completed successfully (No actual submission made)")
                print(f"📊 Results saved to {result.get('report_file', 'job application result file')}")
            else:
                print("✅ Job application completed successfully")
            sys.exit(0)
        else:
            error_msg = result.get('error', 'Unknown error')
            if args.test:
                print(f"❌ Test run failed: {error_msg}")
                print("💡 This was only a test - no actual submission was attempted")
            else:
                print(f"❌ Job application failed: {error_msg}")
            sys.exit(1)
    except ValueError as e:
        # Catch the specific error from initialize_llm if key is missing
        print(f"❌ Configuration Error: {e}")
        logger.error(f"Configuration Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️ Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.exception("Unhandled exception")
        sys.exit(1)

if __name__ == "__main__":
    main() 