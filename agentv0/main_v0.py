import argparse
import json
import logging
import time
import os
from datetime import datetime
import random
import dotenv
from typing import Optional
import sys # Keep sys for potential future use, but comment out path manipulation

# Load environment variables from .env file
dotenv.load_dotenv()

# --- Define Constants Directly (per MVP spec) ---
# MAX_SUBMIT_ATTEMPTS = 1 # Not currently used, but defined for potential future use
# MAX_FIELD_PROCESSING_PASSES = 3 # Limit passes in field processing loop
# LOG_DIR = "logs" # Directory for detailed run logs
# RUN_LOG_FILE = "run_log.jsonl" # File for structured JSONL logs

# --- Add Parent Directory to sys.path --- 
# This allows imports relative to the project root when running main_v0.py directly
script_dir = os.path.dirname(os.path.abspath(__file__))
agentv0_dir = os.path.abspath(script_dir) 
parent_dir = os.path.dirname(agentv0_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# --- Project-level Imports (using agentv0 prefix) ---
from agentv0.strategies.base_strategy import BaseApplicationStrategy
# Platform Strategy factory now imported within select_strategy function

# Import custom modules with aliases for clarity
from agentv0 import browser_controller as agentv0_browser_controller
from agentv0 import action_taker as agentv0_action_taker
# No separate job_scraper module
from agentv0.adaptive_mapper import AdaptiveFieldMapper as agentv0_AdaptiveFieldMapper
from agentv0.probe_page_structure import probe_page_for_llm
from agentv0.config import MAX_SUBMIT_ATTEMPTS, MAX_FIELD_PROCESSING_PASSES, LOG_DIR, RUN_LOG_FILE # Re-enable config import
from agentv0.utils import generate_run_id, setup_logging, append_log, load_profile
from agentv0.strategy_factory import get_strategy 
from agentv0.browser_controller import check_submission_success # Keep specific import

# Comment out sys.path modification - no longer needed
# script_dir = os.path.dirname(os.path.abspath(__file__))
# agentv0_dir = os.path.abspath(script_dir) 
# if agentv0_dir not in sys.path:
#     sys.path.insert(0, agentv0_dir)

# Remove alias imports
# from agentv0 import browser_controller as agentv0_browser_controller, action_taker as agentv0_action_taker, job_scraper
# from agentv0.adaptive_mapper import AdaptiveFieldMapper as agentv0_AdaptiveFieldMapper
# from agentv0.config import MAX_SUBMIT_ATTEMPTS, MAX_FIELD_PROCESSING_PASSES, LOG_DIR
# from agentv0.utils import generate_run_id, setup_logging, append_log, load_profile
# from agentv0.strategy_factory import get_strategy
# from agentv0.browser_controller import check_submission_success # <-- Import added

# --- Logging Setup ---
# Ensure logs directory exists
if not os.path.exists(LOG_DIR): # Use constant from config
    os.makedirs(LOG_DIR)
    
log_file_path = os.path.join(LOG_DIR, f'run_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log') # Use constant from config

# Configure root logger for console output
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - [%(module)s] %(message)s',
                    handlers=[
                        logging.StreamHandler() # Console output
                    ])

# Create a specific logger for JSONL output to run_log.jsonl
run_logger = logging.getLogger('RunLogger')
run_logger.setLevel(logging.INFO)
# Prevent RunLogger messages from propagating to the root logger (which prints to console)
run_logger.propagate = False 
# Add handler for run_log.jsonl (append mode)
jsonl_handler = logging.FileHandler(RUN_LOG_FILE, mode='a') # Use constant from config
jsonl_handler.setLevel(logging.INFO)
# Use a formatter that outputs JSON
class JsonlFormatter(logging.Formatter):
    def format(self, record):
        # Generate ISO 8601 timestamp with milliseconds and Z manually
        now = datetime.utcnow()
        timestamp_str = now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        
        log_entry = {
            'timestamp': timestamp_str,
            'level': record.levelname,
            'message': record.getMessage(),
            **(getattr(record, 'extra_data', {})) # Include extra context data
        }
        return json.dumps(log_entry)

jsonl_handler.setFormatter(JsonlFormatter())
run_logger.addHandler(jsonl_handler)

# Also add a file handler to the root logger for detailed text logs
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.DEBUG) # Log DEBUG level to file
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] %(message)s'))
logging.getLogger().addHandler(file_handler)

# --- Helper Functions ---
def load_profile(file_path: str) -> dict:
    """Loads profile data from a JSON file."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            logging.info(f"Loaded data from {file_path}")
            return data
    except FileNotFoundError:
        logging.error(f"Profile file not found: {file_path}")
        return {}
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from file: {file_path}")
        return {}
    except Exception as e:
        logging.error(f"Error loading profile {file_path}: {e}")
        return {}

def select_strategy(url: str, strategy_name: Optional[str] = None) -> BaseApplicationStrategy:
    """Selects the appropriate strategy based on URL or forced name."""
    # Import locally to avoid circular dependencies if strategies import main utils
    from agentv0.strategies import get_strategy_for_platform 
    
    if strategy_name:
        logging.info(f"Forcing strategy: {strategy_name}")
        platform = strategy_name
    else:
        platform = detect_platform(url) # Detect based on URL
        
    return get_strategy_for_platform(platform)

def append_log(log_file: str, log_entry: dict):
    """Appends a JSON entry to the specified log file."""
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        logging.error(f"Failed to append log entry to {log_file}: {e}")

def log_run_event(event_type: str, data: dict):
    """Helper function to log structured events to run_log.jsonl."""
    base_data = {'event': event_type}
    base_data.update(data)
    # Use 'extra' dict to pass data to the JsonlFormatter
    run_logger.info(f"{event_type} event", extra={'extra_data': base_data})

def detect_platform(url: str) -> str:
    """Detects the ATS platform based on the URL.
       For now, we force 'adaptive' to use the unified strategy.
    """
    # if 'greenhouse.io' in url:
    #     return 'greenhouse'
    # elif 'lever.co' in url:
    #     return 'lever'
    # # Add other platforms like workday, icims, etc. here
    # else:
    #     logging.info(f"Could not definitively identify platform for URL: {url}. Using adaptive strategy.")
    #     return 'adaptive'
    logging.info(f"Forcing Adaptive Strategy for URL: {url}")
    return 'adaptive' # Force adaptive for all URLs now

def main(url: str, profile_path: str, headless: bool = True, strategy_name: Optional[str] = None):
    start_time = time.time()
    final_status = "FAILED"
    failure_reason = "Unknown error"
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") # Restore run_id
    log_path = os.path.join("run_logs", f"run_{run_id}.jsonl") # Define log_path for append_log
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    # Removed call to non-existent setup_logging function

    logging.info(f"--- Starting AgentV0 Run --- URL: {url}")

    playwright = None
    browser = None
    processed_fields_count = 0
    failed_fields_count = 0
    total_fields_attempted = 0
    successfully_processed_selectors = set() # Initialize set for processed selectors

    try:
        # Load profile data (sole source of truth)
        profile_data = load_profile(profile_path)
        if not profile_data:
             raise ValueError(f"Failed to load primary profile from {profile_path}. Cannot proceed.")

        # Initialize mapper directly with the loaded profile
        mapper = agentv0_AdaptiveFieldMapper(profile_data) # Use alias

    # --- Browser Setup --- 
        logging.info("Launching browser...")
        playwright, browser, page = agentv0_browser_controller.launch_browser(headless=headless) # Use alias
        logging.info("Browser launched successfully.")
        
        # --- Navigation --- 
        logging.info(f"Navigating to {url}...")
        nav_success, error_msg = agentv0_browser_controller.navigate_to(page, url) # Use alias
        if not nav_success:
            raise RuntimeError(f"Navigation failed: {error_msg}")
        logging.info(f"Successfully navigated to {url}.")

        # --- Scrape Job/Company Details ---
        job_details = agentv0_browser_controller.scrape_job_details(page) # Use alias
        job_details['url'] = url # Add URL to the details dict
        logging.info(f"Scraped Details: {job_details}")

        # --- Strategy Selection ---
        strategy = select_strategy(url, strategy_name) # Returns an instance
        logging.info(f"Using strategy: {strategy.__class__.__name__}")
        
        # Pass the mapper instance to the strategy 
        if hasattr(strategy, 'set_mapper'):
            strategy.set_mapper(mapper)
        elif hasattr(strategy, 'mapper'): 
            strategy.mapper = mapper 
        else:
            logging.warning("Strategy does not seem to have a mechanism to receive the mapper instance.")

        # --- Initial Apply Click (if needed by strategy) ---
        strategy.perform_initial_apply_click(page)

        # --- Field Identification and Filling Loop ---
        # Use constant for max passes from config
        for pass_num in range(1, MAX_FIELD_PROCESSING_PASSES + 1):
            logging.info(f"Finding fields using strategy (Pass {pass_num})...")
            # Pass the set of successfully processed selectors to find_fields
            identified_fields, probe_map = strategy.find_fields(page, successfully_processed_selectors)
            
            if not identified_fields:
                if pass_num == 1:
                    logging.warning("No fields identified by the strategy in the first pass.")
                    # Potentially try a basic fallback finder here if desired
                else: 
                     logging.info("No new fields identified in this pass.")
                break # Exit loop if no new fields found

            logging.info(f"Processing {len(identified_fields)} identified fields in pass #{pass_num}")
            pass_processed_count = 0
        
        submit_button_selector = None
        fields_to_process = []
            # Separate submit button and fields
            for field in identified_fields:
                if field["key"] == "submit_button":
                    submit_button_selector = field["selector"]
                logging.info(f"Identified submit button via strategy: {submit_button_selector}")
                else:
                    fields_to_process.append(field)

            # --- Process identified fields ---
            for field in fields_to_process:
                profile_key = field["key"]
                selector = field["selector"]
                field_label = field.get("label", "N/A")
                field_type = field.get("type", "unknown")
                total_fields_attempted += 1

                logging.info(f"Attempting to handle field '{profile_key}' ({field_label}) with selector '{selector}'")
                
                # --- Delegate to Strategy's handle_field --- 
                # The strategy now uses its internal mapper instance which has the profile
                try:
                    # Correctly pass the arguments expected by AdaptiveStrategy.handle_field
                    # The strategy will internally use its mapper to get the value
                    # NOTE: The `value` argument passed here might be redundant if strategy re-calculates it, 
                    # but we keep it for now to match the existing signature. Refinement needed later.
                    # For now, pass a placeholder like None, as strategy should recalculate.
                    # Pass the scraped job_details dictionary.
                    success = strategy.handle_field(page, profile_key, selector, None, probe_map, job_details=job_details)
                    
                    # Assuming handle_field now returns True/False for success/failure
                    if success:
                         logging.info(f"Field '{profile_key}' successfully handled by strategy")
                         processed_fields_count += 1
                         pass_processed_count += 1
                         successfully_processed_selectors.add(selector)
                    else:
                         logging.error(f"Strategy reported failure handling field '{profile_key}' ({selector})")
                         failed_fields_count += 1

                except Exception as handle_err:
                    logging.error(f"Error handling field '{profile_key}' ({selector}): {handle_err}", exc_info=True)
                    failed_fields_count += 1

            # End of field processing loop for this pass
            logging.info(f"Processed {pass_processed_count} fields in pass #{pass_num}")
            if pass_processed_count == 0 and pass_num > 1:
                logging.info("No new fields were successfully processed in this pass. Ending field processing.")
                break # Stop if a pass yields no new successfully processed fields
            
            # Optional: Add delay between passes?
            # add_random_delay(1.0, 2.0) # Removed this problematic call
        
        # --- Final Submission Attempt ---
        logging.info("Attempting to submit application...")
        strategy.perform_pre_submit_steps(page) # Perform any checks before final submit
        
        submit_success = False
        if submit_button_selector:
            logging.info(f"Attempting submit using strategy-identified selector: {submit_button_selector}")
            submit_success = agentv0_action_taker.click_button(page, submit_button_selector) # Use alias
        else:
            # Fallback submit attempt if strategy didn't find one
            logging.warning("Strategy did not identify a submit button. Trying common fallbacks.")
            fallback_submit_selectors = [
                 "button[type='submit']", "input[type='submit']", 
                 "button:has-text('Submit')", "button:has-text('Apply')",
                 "button:has-text('Submit Application')" 
            ]
            for fb_selector in fallback_submit_selectors:
                if agentv0_action_taker.click_button(page, fb_selector): # Use alias
                    submit_success = True
                    break
        if not submit_success:
                 logging.error("Could not find or click any submit button.")
                 failure_reason = "Submit button not found or click failed"

        if submit_success:
            logging.info("Submit action successful! Waiting and checking for confirmation...")
            # Add a longer wait to allow for page navigation/confirmation
            page.wait_for_timeout(5000) 
            
            # --- Check for Submission Success Confirmation ---
            logging.info("Checking for submission success confirmation...")
            is_confirmed_success, confirmation_details = check_submission_success(page) 
            
            if is_confirmed_success:
                logging.info(f"Submission success confirmed: {confirmation_details}")
                final_status = "SUCCESS"
                failure_reason = None # Clear failure reason on confirmed success
            else:
                logging.warning(f"Submit button clicked, but success confirmation not found. Details: {confirmation_details}")
                final_status = "FAILED" # Mark as failed if confirmation missing
                failure_reason = "Submission confirmation check failed"
                # Optionally log the state of the page for debugging
                try:
                    page_content = page.content()
                    logging.debug(f"Page content after failed confirmation check: {page_content[:500]}...") # Log first 500 chars
                except Exception as content_err:
                    logging.error(f"Could not get page content after failed confirmation: {content_err}")
        else:
            final_status = "FAILED"
            # Keep the existing logic for setting failure_reason if submit_success was False
            if failure_reason == "Unknown error" or not failure_reason: # Update reason if not already set more specifically
                 failure_reason = "Submit action failed or button not found"

    except ValueError as val_err: # Catch specific error for failed profile load
        logging.error(f"Configuration Error: {val_err}")
        final_status = "FAILED"
        failure_reason = str(val_err)
    except RuntimeError as rt_err:
        logging.error(f"Runtime Error: {rt_err}", exc_info=True)
        final_status = "FAILED"
        failure_reason = str(rt_err)
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        final_status = "FAILED"
        failure_reason = f"Unexpected error: {type(e).__name__}"
    finally:
        # --- Logging Summary ---
        end_time = time.time()
        duration = end_time - start_time
        success_rate = (processed_fields_count / total_fields_attempted * 100) if total_fields_attempted > 0 else 0
        log_summary = {
            "run_id": run_id, # Use the defined run_id
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "profile": profile_path,
            "status": final_status,
            "duration_seconds": round(duration, 2),
            "total_fields_attempted": total_fields_attempted,
            "processed_fields_count": processed_fields_count,
            "failed_fields_count": failed_fields_count,
            "action_success_rate_percent": round(success_rate, 1),
            "failure_reason": failure_reason
        }
        append_log(log_path, log_summary) # Use the defined log_path
        logging.info(f"--- AgentV0 Run Finished --- Status: {final_status}, Duration: {duration:.2f}s")
        if failure_reason: logging.info(f"Failure Reason: {failure_reason}")
        logging.info(f"Field Stats: Attempted={total_fields_attempted}, Succeeded={processed_fields_count}, Failed={failed_fields_count}, Success Rate={success_rate:.1f}%")

        # --- Browser Cleanup ---
        if browser:
            logging.info("Closing browser...")
            agentv0_browser_controller.close_browser(playwright, browser) # Use alias
            logging.info("Browser closed successfully.")
        elif playwright: # Ensure playwright is stopped even if browser fails
            try:
                 playwright.stop()
                 logging.info("Playwright stopped.")
            except Exception as stop_err:
                 logging.error(f"Error stopping playwright: {stop_err}")
                 
    return final_status == "SUCCESS"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentV0: Automated Job Application Submission")
    parser.add_argument("url", help="Target job application URL")
    parser.add_argument("profile_path", help="Path to the profile JSON file")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True, help="Run browser in headless mode (default: True)")
    args = parser.parse_args()

    main(args.url, args.profile_path, headless=args.headless)
