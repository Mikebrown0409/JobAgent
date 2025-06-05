#!/usr/bin/env python3

import argparse
import asyncio
import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# Ensure agentv0 is in the path if running main.py directly from root
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agentv0.agent_core import AgentCore, TaskStatus

# Load environment variables from .env file
load_dotenv()

# Basic Logging Setup (AgentCore and other modules will have more specific logging)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)] # Log to console
)
logger = logging.getLogger("main")

async def run_agent():
    """Parses arguments, initializes AgentCore, runs the task, and saves results."""
    parser = argparse.ArgumentParser(description="Run the AgentV0 job application agent.")
    parser.add_argument("--url", required=True, help="URL of the job posting to apply for.")
    parser.add_argument("--profile", default="profile.json",
                        help="Path to the user profile JSON file (default: profile.json)")
    parser.add_argument("--headless", action="store_true",
                        help="Run the browser in headless mode (no UI). Defaults to true if not specified.")
    parser.add_argument("--no-headless", action="store_false", dest="headless",
                        help="Run the browser with a visible UI.")
    parser.add_argument("--output-dir", default="run_results",
                        help="Directory to save run results JSON (default: run_results)")
    parser.set_defaults(headless=True) # Headless by default

    args = parser.parse_args()

    # Construct the goal for the agent
    goal = f"Apply to the job listed at the following URL: {args.url}"
    logger.info(f"Goal: {goal}")
    logger.info(f"Profile: {args.profile}")
    logger.info(f"Headless mode: {args.headless}")

    # --- Output Setup ---
    try:
        os.makedirs(args.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize URL for filename (basic example)
        sanitized_url_part = args.url.split('//')[-1].split('/')[0].replace('.', '_')[:50]
        output_filename = f"run_{timestamp}_{sanitized_url_part}.json"
        output_path = os.path.join(args.output_dir, output_filename)
        logger.info(f"Saving results to: {output_path}")
    except Exception as e:
        logger.error(f"Failed to create output directory or filename: {e}")
        return 2 # Indicate failure

    # --- Agent Initialization and Execution ---
    status = TaskStatus.FAILED # Default status
    try:
        # Check if profile exists before initializing agent
        if not os.path.exists(args.profile):
             logger.error(f"Profile file not found: {args.profile}")
             raise FileNotFoundError(f"Profile file not found: {args.profile}")

        agent = AgentCore(
            profile_path=args.profile,
            # fallback_path=None, # Not using fallback for now
            headless=args.headless
        )

        # Execute the task
        status = await agent.execute_task(goal)

        # Save results
        agent.save_results(output_path)

    except FileNotFoundError as e:
         # Already logged error, just ensure status is FAILED
         status = TaskStatus.FAILED
    except Exception as e:
        logger.error(f"An unexpected error occurred during agent execution: {e}", exc_info=True)
        status = TaskStatus.FAILED
        # Attempt to save whatever state exists if agent was initialized
        if 'agent' in locals():
            try:
                 logger.info("Attempting to save partial results after error...")
                 agent.save_results(output_path.replace('.json', '_error.json'))
            except Exception as save_err:
                 logger.error(f"Could not save error state: {save_err}")


    # --- Return Exit Code ---
    if status == TaskStatus.SUCCEEDED:
        logger.info("Task completed successfully")
        return 0
    elif status == TaskStatus.PARTIALLY_SUCCEEDED:
        logger.warning("Task completed with partial success")
        return 1
    else:
        logger.error("Task failed")
        return 2

if __name__ == "__main__":
    # Ensure the script runs from the workspace root for consistent relative paths
    workspace_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(workspace_root)
    logger.info(f"Running from workspace root: {os.getcwd()}")

    exit_code = asyncio.run(run_agent())
    sys.exit(exit_code) 