#!/usr/bin/env python3

"""
Test script to verify configuration and dependencies for the job application agent.
Run this script to ensure all components are working properly before attempting job applications.
"""

import os
import sys
import json
import logging
from pathlib import Path
import importlib.util

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("SetupTest")

def check_env_file():
    """Check if .env file exists and contains required API keys."""
    env_path = Path(__file__).parent.parent / '.env'
    
    if not env_path.exists():
        logger.error(f".env file not found at {env_path}")
        logger.info("Creating sample .env file...")
        
        with open(env_path, 'w') as f:
            f.write("# API Keys\n")
            f.write("GEMINI_API_KEY=your_api_key_here\n")
            f.write("OPENAI_API_KEY=your_api_key_here\n")
        
        logger.info(f"Sample .env file created at {env_path}. Please edit it with your actual API keys.")
        return False
    
    # Check if API keys are set
    with open(env_path, 'r') as f:
        env_content = f.read()
    
    has_gemini = "GEMINI_API_KEY" in env_content and "your_api_key_here" not in env_content
    has_openai = "OPENAI_API_KEY" in env_content and "your_api_key_here" not in env_content
    
    if not has_gemini:
        logger.error("GEMINI_API_KEY not set in .env file")
    
    if not has_openai:
        logger.warning("OPENAI_API_KEY not set in .env file (optional)")
    
    return has_gemini

def check_python_dependencies():
    """Check if required Python packages are installed."""
    required_packages = [
        "playwright",
        "google.generativeai",
        "openai",
        "pydantic",
        "bs4",  # beautifulsoup4
        "dotenv",
        "tqdm",
        "aiohttp",
        "joblib"
    ]
    
    missing = []
    for package in required_packages:
        try:
            importlib.import_module(package.replace('-', '_'))
        except ImportError:
            missing.append(package)
    
    if missing:
        logger.error(f"Missing Python packages: {', '.join(missing)}")
        logger.info("Install them using: pip install -r requirements.txt")
        return False
    
    logger.info("All required Python packages are installed.")
    return True

def check_profile():
    """Check if profile.json exists and has required fields."""
    profile_path = Path(__file__).parent / "profile.json"
    
    if not profile_path.exists():
        logger.error(f"profile.json not found at {profile_path}")
        logger.info("Please create a profile.json file using setup_profile.py")
        return False
    
    try:
        with open(profile_path, 'r') as f:
            profile = json.load(f)
    except json.JSONDecodeError:
        logger.error("profile.json is not valid JSON")
        return False
    
    # Check if basic required fields are present
    required_fields = [
        ("basics", "name"),
        ("basics", "email"),
        ("basics", "phone")
    ]
    
    missing = []
    for section, field in required_fields:
        if section not in profile or not profile[section].get(field):
            missing.append(f"{section}.{field}")
    
    if missing:
        logger.error(f"Missing required fields in profile.json: {', '.join(missing)}")
        return False
    
    logger.info("profile.json exists and contains required fields.")
    return True

def check_playwright_browsers():
    """Check if Playwright browsers are installed."""
    from playwright.sync_api import sync_playwright
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
        logger.info("Playwright browsers are installed.")
        return True
    except Exception as e:
        logger.error(f"Playwright browser check failed: {e}")
        logger.info("Install Playwright browsers using: playwright install")
        return False

def check_jobs_file():
    """Check if jobs.txt exists and contains job URLs."""
    jobs_path = Path(__file__).parent / "jobs.txt"
    
    if not jobs_path.exists():
        logger.warning(f"jobs.txt not found at {jobs_path}")
        logger.info("Creating sample jobs.txt file...")
        
        with open(jobs_path, 'w') as f:
            f.write("# Add job URLs here, one per line\n")
            f.write("# Example: https://boards.greenhouse.io/example/jobs/12345\n")
        
        logger.info(f"Sample jobs.txt file created at {jobs_path}. Please edit it with actual job URLs.")
        return False
    
    with open(jobs_path, 'r') as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    
    if not lines:
        logger.warning("jobs.txt exists but contains no job URLs")
        return False
    
    logger.info(f"jobs.txt exists and contains {len(lines)} job URLs.")
    return True

def main():
    """Run all setup tests."""
    logger.info("Starting setup verification...")
    
    results = {
        "Environment file": check_env_file(),
        "Python dependencies": check_python_dependencies(),
        "Profile file": check_profile(),
        "Playwright browsers": check_playwright_browsers(),
        "Jobs file": check_jobs_file()
    }
    
    # Print summary
    print("\n" + "=" * 50)
    print("Setup Verification Summary".center(50))
    print("=" * 50)
    
    all_pass = True
    for test, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        if not result:
            all_pass = False
        print(f"{test:<25}: {status}")
    
    print("\n")
    if all_pass:
        print("All checks passed! You're ready to run the job application agent.")
        print("Try running: python process_jobs.py --single-url \"your_job_url_here\"")
    else:
        print("Some checks failed. Please address the issues listed above before running the agent.")
    
    return all_pass

if __name__ == "__main__":
    sys.exit(0 if main() else 1) 