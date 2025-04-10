#!/usr/bin/env python3

import os
import sys
import time
import logging
import json
import argparse
from datetime import datetime
from typing import List, Dict, Any
from main_v0 import main

# Configure logging
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "run_results")
os.makedirs(LOG_DIR, exist_ok=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, f"job_processor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"))
    ]
)
logger = logging.getLogger("JobProcessor")

def read_job_urls(file_path: str) -> List[str]:
    """Read job URLs from the specified file, skipping empty lines."""
    with open(file_path, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def log_job_result(job_url: str, status: str, error: str = None, duration: float = 0):
    """Log the result of a job application attempt."""
    result = {
        "job_url": job_url,
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "duration_seconds": duration
    }
    if error:
        result["error"] = error
    
    # Create a unique filename for each job result
    job_id = job_url.split('/')[-2] if len(job_url.split('/')) > 2 else "unknown"
    result_file = os.path.join(
        LOG_DIR, 
        f"job_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{job_id}.json"
    )
    
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    logger.info(f"Job result saved to {result_file}")

def process_jobs(job_urls: List[str], profile_path: str, headless: bool = True, delay: int = 5, 
                start_index: int = 0, max_jobs: int = None, retry_failed: bool = False):
    """Process each job URL using main_v0.py."""
    # Apply limits
    if start_index > 0:
        job_urls = job_urls[start_index:]
    
    if max_jobs:
        job_urls = job_urls[:max_jobs]
        
    total_jobs = len(job_urls)
    successful = 0
    failed = 0
    failed_jobs = []
    
    logger.info(f"Starting to process {total_jobs} jobs from index {start_index}")
    
    for index, url in enumerate(job_urls):
        job_number = index + 1 + start_index
        logger.info(f"Processing job {job_number}/{total_jobs + start_index}: {url}")
        
        start_time = time.time()
        try:
            # Call the main function from main_v0.py
            main(url, profile_path, headless=headless)
            status = "SUCCESS"
            successful += 1
            error = None
        except Exception as e:
            status = "FAILED"
            failed += 1
            error = str(e)
            failed_jobs.append({"url": url, "error": error})
            logger.error(f"Error processing job {url}: {e}", exc_info=True)
        
        duration = time.time() - start_time
        logger.info(f"Job {job_number}/{total_jobs + start_index} completed with status: {status} in {duration:.2f} seconds")
        log_job_result(url, status, error, duration)
        
        # Add a delay between jobs to prevent rate limiting
        if job_number < total_jobs + start_index:
            logger.info(f"Waiting {delay} seconds before processing the next job...")
            time.sleep(delay)
    
    logger.info(f"Job processing completed: {successful} successful, {failed} failed, {total_jobs} total")
    
    # Handle retrying failed jobs
    if retry_failed and failed_jobs:
        logger.info(f"Retrying {len(failed_jobs)} failed jobs...")
        retry_urls = [job["url"] for job in failed_jobs]
        retry_successful, retry_failed, retry_total = process_jobs(
            retry_urls, profile_path, headless, delay, 0, None, False
        )
        successful += retry_successful
        failed = retry_failed  # Only count failures from the retry
        
        logger.info(f"After retries: {successful} successful, {failed} failed, {total_jobs} total")
    
    return successful, failed, total_jobs

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Process job applications using main_v0.py")
    
    parser.add_argument("--jobs-file", default="jobs.txt",
                        help="Path to the file containing job URLs (default: jobs.txt)")
    
    parser.add_argument("--profile", default="profile.json",
                        help="Path to the profile JSON file (default: profile.json)")
    
    parser.add_argument("--headless", action="store_true",
                        help="Run in headless mode (browser not visible)")
    
    parser.add_argument("--delay", type=int, default=5,
                        help="Delay in seconds between processing jobs (default: 5)")
    
    parser.add_argument("--start-index", type=int, default=0,
                        help="Start processing from this index (default: 0)")
    
    parser.add_argument("--max-jobs", type=int, default=None,
                        help="Maximum number of jobs to process (default: all)")
    
    parser.add_argument("--retry-failed", action="store_true",
                        help="Retry failed jobs after initial run")
    
    parser.add_argument("--single-url", default=None,
                        help="Process a single URL instead of reading from jobs file")
    
    return parser.parse_args()

def main_processor():
    """Main function to process all jobs."""
    args = parse_arguments()
    
    # Path to the jobs file
    jobs_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.jobs_file)
    
    # Path to the profile file
    profile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.profile)
    
    # Check if profile exists
    if not os.path.exists(profile_path):
        logger.error(f"Profile file not found: {profile_path}")
        return
    
    # Get job URLs
    if args.single_url:
        job_urls = [args.single_url]
        logger.info(f"Processing single URL: {args.single_url}")
    else:
        # Check if jobs file exists
        if not os.path.exists(jobs_file):
            logger.error(f"Jobs file not found: {jobs_file}")
            return
        
        # Read job URLs
        job_urls = read_job_urls(jobs_file)
        logger.info(f"Read {len(job_urls)} job URLs from {jobs_file}")
    
    # Process jobs
    successful, failed, total = process_jobs(
        job_urls, 
        profile_path, 
        headless=args.headless,
        delay=args.delay,
        start_index=args.start_index,
        max_jobs=args.max_jobs,
        retry_failed=args.retry_failed
    )
    
    # Print summary
    print("\nJob Processing Summary:")
    print(f"Total Jobs: {total}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    if total > 0:
        print(f"Success Rate: {(successful/total)*100:.2f}%")

if __name__ == "__main__":
    main_processor() 