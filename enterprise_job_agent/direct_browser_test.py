#!/usr/bin/env python3
"""
Direct browser test for Discord application form.
This test bypasses the ActionExecutor and uses Playwright directly.
"""

import os
import sys
import asyncio
import logging
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

async def main():
    """Main test function that directly uses Playwright to fill the Discord form."""
    # Discord job application URL
    discord_url = "https://job-boards.greenhouse.io/discord/jobs/7845336002"
    
    # Test user data
    user_data = {
        "first_name": "Alex",
        "last_name": "Chen",
        "email": "alex.chen@example.com",
        "phone": "555-123-4567",
        "location": "San Francisco, California, United States",
        "linkedin": "https://linkedin.com/in/alexchen",
        "school": "University of California, Berkeley",
        "degree": "Bachelor of Science",
        "discipline": "Computer Science",
        "why_discord": "I am very interested in this opportunity because I've been using Discord for years and deeply value the platform's impact on community building. I'm excited to contribute to a product that millions of people use daily.",
    }
    
    logger.info("Starting direct browser test for Discord application")
    
    async with async_playwright() as p:
        # Launch browser with visible UI
        browser = await p.chromium.launch(headless=False)
        
        # Create a new browser context
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.93 Safari/537.36'
        )
        
        # Create a new page
        page = await context.new_page()
        logger.info(f"Navigating to {discord_url}")
        
        # Go to Discord job application page
        await page.goto(discord_url, wait_until="networkidle", timeout=60000)
        
        # Wait for the form to load
        await page.wait_for_selector("form", timeout=10000)
        logger.info("Form loaded")
        
        # Fill basic information fields
        logger.info("Filling personal information")
        await fill_field(page, "#first_name", user_data["first_name"])
        await fill_field(page, "#last_name", user_data["last_name"])
        await fill_field(page, "#email", user_data["email"])
        await fill_field(page, "#phone", user_data["phone"])
        
        # Handle location (typeahead)
        logger.info("Filling location field (typeahead)")
        await fill_typeahead(page, "#candidate-location", user_data["location"])
        
        # School information (typeahead)
        logger.info("Filling education fields (typeahead)")
        await fill_typeahead(page, "#school--0", user_data["school"])
        await fill_typeahead(page, "#degree--0", user_data["degree"])
        await fill_typeahead(page, "#discipline--0", user_data["discipline"])
        
        # Answer custom questions
        logger.info("Filling custom questions")
        # Why Discord question
        await fill_field(page, "#question_30608968002", user_data["why_discord"])
        # How heard about job 
        await fill_field(page, "#question_30608971002", "LinkedIn")
        # LinkedIn profile
        await fill_field(page, "#question_30608969002", user_data["linkedin"])
        
        # Handle dropdown selections - Work authorization questions
        logger.info("Handling dropdown selections")
        await select_dropdown(page, "#question_30608972002", "Yes")  # Legally authorized to work
        await select_dropdown(page, "#question_30608973002", "Yes")  # Currently located in US
        
        # Diversity questions
        await select_dropdown(page, "#gender", "Male")
        await select_dropdown(page, "#hispanic_ethnicity", "No")
        await select_dropdown(page, "#veteran_status", "I am not a protected veteran")
        await select_dropdown(page, "#disability_status", "No, I don't have a disability and have not had one in the past")
        
        # Wait to observe the filled form
        logger.info("Form filled successfully - waiting for observation")
        await asyncio.sleep(60)  # Wait 1 minute to observe the filled form
        
        # Close the browser
        await browser.close()
        logger.info("Test completed")

async def fill_field(page, selector, value):
    """Fill a text field."""
    try:
        await page.fill(selector, value)
        logger.info(f"Filled {selector} with '{value}'")
        await asyncio.sleep(0.5)  # Small delay for visibility
        return True
    except Exception as e:
        logger.error(f"Error filling {selector}: {e}")
        return False

async def fill_typeahead(page, selector, value):
    """Fill a typeahead field and select the first option."""
    try:
        # Click the field to focus it
        await page.click(selector)
        await asyncio.sleep(0.3)
        
        # Clear existing value if any
        await page.fill(selector, "")
        await asyncio.sleep(0.2)
        
        # Type the value slowly to trigger suggestions
        for i in range(0, len(value), 3):
            chunk = value[i:i+3]
            await page.type(selector, chunk, delay=100)
            await asyncio.sleep(0.3)
        
        # Wait for suggestions dropdown
        await asyncio.sleep(1)
        
        # Try to select first option by pressing Enter
        await page.keyboard.press("Enter")
        await asyncio.sleep(0.5)
        
        logger.info(f"Filled typeahead {selector} with '{value}'")
        return True
    except Exception as e:
        logger.error(f"Error filling typeahead {selector}: {e}")
        return False

async def select_dropdown(page, selector, option_text):
    """Select option from a dropdown by text."""
    try:
        # Click to open dropdown
        await page.click(selector)
        await asyncio.sleep(0.5)
        
        # Try to find and click the option by text
        option_selector = f"text='{option_text}'"
        try:
            # Try to find the option with exact text
            await page.click(option_selector, timeout=3000)
        except:
            # If exact match fails, try to find option containing the text
            partial_selector = f"text='{option_text}'"
            await page.click(partial_selector, timeout=3000)
        
        await asyncio.sleep(0.5)
        logger.info(f"Selected '{option_text}' from dropdown {selector}")
        return True
    except Exception as e:
        logger.error(f"Error selecting from dropdown {selector}: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(main()) 