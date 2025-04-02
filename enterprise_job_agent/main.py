"""Main module for the enterprise job application system."""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import difflib
from typing import Dict, Any, Optional
import re
import uuid
from datetime import datetime

# LLM imports
from langchain_openai import ChatOpenAI as LangchainChatOpenAI
from together import Together
from crewai import Agent, Task, Crew
from playwright.async_api import async_playwright, Page, Locator, Frame
import google.generativeai as genai
from crewai.tasks.task_output import TaskOutput

# Local imports
from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.job_extractor import extract_job_data
from enterprise_job_agent.core.profile_manager import ProfileManager
from enterprise_job_agent.core.crew_manager import JobApplicationCrew
from enterprise_job_agent.core.frame_manager import AdvancedFrameManager

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

def initialize_llm(api_key=None, use_gemini=True, use_openai=False, use_together=False):
    """Initialize the language model.
    
    Args:
        api_key: The API key for the model.
        use_gemini: Whether to use Google's Gemini model (default).
        use_openai: Whether to use OpenAI's model.
        use_together: Whether to use Together AI's model.
        
    Returns:
        The initialized model.
        
    Raises:
        ValueError: If the API key is not provided when required.
    """
    if use_gemini:
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("Gemini API key is required. Set GEMINI_API_KEY environment variable.")
        
        # Configure the Gemini API
        genai.configure(api_key=api_key)
        logger.debug("Configured Google Generative AI with provided API key")
        
        # Create a custom CrewAI-compatible Gemini model wrapper
        class GeminiWrapper:
            def __init__(self, model_name="gemini-2.0-flash"):
                self.model = genai.GenerativeModel(model_name, 
                                                   generation_config={
                                                       "temperature": 0.4,  # Lower for more consistency
                                                       "top_p": 0.95,
                                                       "top_k": 40,
                                                       "max_output_tokens": 4096,  # Adjust to balance between thoroughness and speed
                                                   })
                self.model_name = model_name
                self.request_counter = 0
                self.rate_limit = 60  # requests per minute
                self.last_request_time = 0
                logger.info(f"Initialized Gemini model: {model_name}")
                
                # Properties required for CrewAI compatibility
                self.model_name = model_name
                self.is_chat_model = True
                self.is_function_calling_available = False
                self.stop = None
                self.temperature = 0.4
                
                # Log debug information 
                logger.debug(f"GeminiWrapper initialized with model_name: {self.model_name}")
                logger.debug(f"GeminiWrapper model object: {self.model}")
            
            def invoke(self, messages):
                """Convert CrewAI message format to Gemini format and invoke the model."""
                try:
                    # Simple rate limiting to respect Gemini's limits
                    now = time.time()
                    if now - self.last_request_time < 1 and self.request_counter >= self.rate_limit:
                        sleep_time = 1 - (now - self.last_request_time)
                        logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
                        time.sleep(sleep_time)
                        self.request_counter = 0
                        
                    # Format messages for Gemini
                    prompt = self._format_messages(messages)
                    logger.debug(f"Sending prompt to Gemini: {prompt[:100]}...")
                    
                    # Generate content
                    response = self.model.generate_content(prompt)
                    
                    # Update rate limiting tracking
                    self.request_counter += 1
                    self.last_request_time = time.time()
                    
                    if not response.text:
                        logger.warning("Empty response from Gemini")
                        return "I couldn't generate a response. Please try again with different instructions."
                    
                    logger.debug(f"Received response from Gemini: {response.text[:100]}...")
                    return response.text
                    
                except Exception as e:
                    logger.error(f"Error invoking Gemini model: {str(e)}")
                    # Return error message that won't break JSON parsing
                    return f"Error: {str(e)}"
            
            def _format_messages(self, messages):
                """Format CrewAI messages for Gemini."""
                # Extract system message if present
                system_content = ""
                user_content = ""
                
                for message in messages:
                    role = message.get("role", "")
                    content = message.get("content", "")
                    
                    if role == "system":
                        system_content = content
                    elif role == "user":
                        user_content = content
                    # We ignore assistant messages as Gemini Flash doesn't use chat history
                
                # Combine system and user content for Gemini
                if system_content and user_content:
                    formatted_prompt = f"Instructions: {system_content}\n\nTask: {user_content}"
                elif system_content:
                    formatted_prompt = system_content
                else:
                    formatted_prompt = user_content
                
                return formatted_prompt
            
            # Required methods for CrewAI compatibility
            def supports_stop_words(self):
                """Check if the model supports stop words."""
                logger.debug("supports_stop_words() called")
                return False
                
            def get_model_name(self):
                """Get the model name."""
                logger.debug(f"get_model_name() called, returning: {self.model_name}")
                return self.model_name
                
            def supports_function_calling(self):
                """Check if the model supports function calling."""
                logger.debug("supports_function_calling() called")
                return False
                
            def supports_streaming(self):
                """Check if the model supports streaming."""
                logger.debug("supports_streaming() called")
                return False
                
            def lower(self):
                """Return a lowercase version of the model name."""
                logger.debug(f"lower() called, returning: {str(self.model_name).lower()}")
                return str(self.model_name).lower()
                
            def dict(self):
                """Return a dictionary representation for serialization."""
                result = {
                    "model_name": self.model_name,
                    "is_chat_model": True,
                    "temperature": 0.4
                }
                logger.debug(f"dict() called, returning: {result}")
                return result
                
            def __str__(self):
                """Return a string representation."""
                return f"GeminiWrapper(model_name={self.model_name})"
                
            # Make the wrapper callable like a CrewAI agent's LLM
            def __call__(self, messages):
                """Make the wrapper callable like a CrewAI agent's LLM."""
                logger.debug(f"__call__ method called with messages: {messages[:100]}...")
                response_text = self.invoke(messages)
                return {"content": response_text}
        
        return GeminiWrapper()
    
    elif use_openai:
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")
        
        return LangchainChatOpenAI(
            api_key=api_key,
            model="gpt-4o",
            temperature=0.7
        )
    elif use_together:
        # Fallback to Together AI
        if not api_key:
            api_key = os.getenv("TOGETHER_API_KEY")
            if not api_key:
                api_key = "2cb66c457552f0b183e873f5b2594b732c7cef71733c5a0eb92ab47fdd88e1b5"
                logger.warning("Using default Together API key. Set TOGETHER_API_KEY for production.")
        
        logger.info("Initializing Together AI with Llama 3")
        client = Together(api_key=api_key)
        return client
    else:
        # Fallback to Together AI
        if not api_key:
            api_key = os.getenv("TOGETHER_API_KEY")
            if not api_key:
                api_key = "2cb66c457552f0b183e873f5b2594b732c7cef71733c5a0eb92ab47fdd88e1b5"
        
        client = Together(api_key=api_key)
        return client

async def run_job_application(
    job_url: str,
    profile_path: Optional[str] = None,
    api_key: Optional[str] = None,
    headless: bool = True,
    test_mode: bool = False,
    verbose: bool = False,
    use_together: bool = False,
    use_langchain_gemini: bool = False,
    langchain_llm = None
) -> Dict[str, Any]:
    """
    Run the job application process using Gemini Flash 2.0.
    
    Args:
        job_url: URL of the job posting
        profile_path: Path to user profile JSON
        api_key: Gemini API key (defaults to GEMINI_API_KEY env variable)
        headless: Whether to run the browser in headless mode
        test_mode: Whether to run in test mode (no actual submission)
        verbose: Whether to enable verbose logging
        use_together: Whether to use the Together API instead of Gemini
        use_langchain_gemini: Whether to use LangChain's Gemini integration 
        langchain_llm: Pre-configured LangChain LLM to use
        
    Returns:
        Results of the job application process
    """
    logger.info(f"Starting job application process for {job_url}")
    if test_mode:
        logger.info("RUNNING IN TEST MODE - No job application will be submitted")
    
    # Initialize the language model
    if use_langchain_gemini and langchain_llm:
        logger.info("Using LangChain's Gemini integration for CrewAI compatibility")
        llm = langchain_llm
    elif use_together:
        logger.info("Using Together AI for CrewAI compatibility")
        llm = initialize_llm(api_key, use_gemini=False, use_openai=False, use_together=True)
    else:
        # Initialize Gemini as the language model
        logger.info("Using Gemini as the language model")
        llm = initialize_llm(api_key, use_gemini=True)
    
    # Load user profile
    profile_manager = ProfileManager(profile_path)
    user_profile = profile_manager.get_profile()
    
    # Create a unique ID for this job application process
    job_id = str(uuid.uuid4())[:8]
    logger.info(f"Job application ID: {job_id}")
    
    # Create output directory for results - using absolute path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(script_dir, f"test_results/job_{job_id}")
    os.makedirs(results_dir, exist_ok=True)
    logger.info(f"Created results directory: {results_dir}")
    
    # --- Centralized Browser Manager Initialization --- 
    browser_manager = None # Define here for finally block access
    frame_manager = None
    try:
        # Instantiate managers
        # Frame manager needs page, so start browser first
        temp_bm_for_startup = BrowserManager(headless=headless)
        if not await temp_bm_for_startup.start():
             logger.error("Failed to start browser during initial setup")
             return {"success": False, "error": "Browser startup failed"}
             
        page = await temp_bm_for_startup.get_page()
        frame_manager = AdvancedFrameManager(page)
        # Create the main browser manager, passing the frame manager
        browser_manager = BrowserManager(headless=headless, frame_manager=frame_manager)
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
        logger.error(f"Error in job application process: {str(e)}")
        logger.exception("Exception details:")
        
        # Save error information
        error_file = f"{results_dir}/error.json"
        try:
            with open(error_file, "w") as f:
                json.dump({
                    "error": str(e),
                    "job_id": job_id,
                    "test_mode": test_mode,
                    "timestamp": datetime.now().isoformat()
                }, f, indent=2)
            logger.info(f"Error details saved to {error_file}")
        except Exception as write_error:
            logger.warning(f"Failed to save error details: {write_error}")
        
        return {
            "success": False, 
            "error": str(e), 
            "job_id": job_id, 
            "test_mode": test_mode,
            "results_dir": results_dir
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
    
    args = parser.parse_args()
    
    try:
        if args.test:
            print("🧪 RUNNING IN TEST MODE - No actual job application will be submitted")
            logger.info("Test mode enabled - application will not be submitted")
        
        print(f"⏳ Processing job application for URL: {args.job_url}")
        if args.visible:
            print("🔍 Browser will be visible during execution")
            
        # Set default profile path if not provided
        profile_path = args.profile or "test_user/user_profile.json"
        
        # Run the job application process
        result = asyncio.run(run_job_application(
            job_url=args.job_url,
            profile_path=profile_path,
            api_key=args.api_key,
            headless=not args.visible,
            test_mode=args.test,
            verbose=args.verbose
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
    except KeyboardInterrupt:
        print("\n⚠️ Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.exception("Unhandled exception")
        sys.exit(1)

if __name__ == "__main__":
    main() 