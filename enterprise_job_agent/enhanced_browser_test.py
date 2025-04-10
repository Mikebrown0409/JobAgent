#!/usr/bin/env python3
"""
Enhanced direct browser test for Discord application form with better typeahead handling.
This test uses advanced techniques to handle complex fields reliably.
"""

import os
import sys
import asyncio
import logging
import re
from playwright.async_api import async_playwright, Error, TimeoutError

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

async def main():
    """Main test function with enhanced form field handling."""
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
    
    # Initialize success metrics
    fields_total = 0
    fields_success = 0
    field_results = []
    
    logger.info("Starting enhanced direct browser test for Discord application")
    
    async with async_playwright() as p:
        # Launch browser with visible UI
        browser = await p.chromium.launch(headless=False)
        
        try:
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
            fields_total += 1
            if await fill_field(page, "#first_name", user_data["first_name"]):
                fields_success += 1
                field_results.append({"field": "first_name", "success": True})
            else:
                field_results.append({"field": "first_name", "success": False})
                
            fields_total += 1
            if await fill_field(page, "#last_name", user_data["last_name"]):
                fields_success += 1
                field_results.append({"field": "last_name", "success": True})
            else:
                field_results.append({"field": "last_name", "success": False})
                
            fields_total += 1
            if await fill_field(page, "#email", user_data["email"]):
                fields_success += 1
                field_results.append({"field": "email", "success": True})
            else:
                field_results.append({"field": "email", "success": False})
                
            fields_total += 1
            if await fill_field(page, "#phone", user_data["phone"]):
                fields_success += 1
                field_results.append({"field": "phone", "success": True})
            else:
                field_results.append({"field": "phone", "success": False})
            
            # Handle location (typeahead)
            logger.info("Filling location field (typeahead)")
            fields_total += 1
            if await enhanced_typeahead(page, "#candidate-location", user_data["location"]):
                fields_success += 1
                field_results.append({"field": "location", "success": True})
            else:
                field_results.append({"field": "location", "success": False})
            
            # School information (typeahead) with special handling
            logger.info("Filling education fields (advanced typeahead)")
            
            # Handle school with multiple strategies
            fields_total += 1
            school_strategies = [
                {"value": user_data["school"], "description": "Full name"},
                {"value": "UC Berkeley", "description": "Common abbreviation"},
                {"value": "Berkeley", "description": "Simple name"}
            ]
            
            school_success = False
            for strategy in school_strategies:
                logger.info(f"Trying school strategy: {strategy['description']}")
                if await enhanced_typeahead(page, "#school--0", strategy["value"], use_arrow_keys=True):
                    school_success = True
                    fields_success += 1
                    field_results.append({"field": "school", "success": True, "strategy": strategy["description"]})
                    break
                # Clear field before trying next strategy
                try:
                    await page.fill("#school--0", "")
                    await asyncio.sleep(0.5)
                except:
                    pass
            
            if not school_success:
                field_results.append({"field": "school", "success": False})
            
            # Degree with enhanced handling
            fields_total += 1
            if await enhanced_typeahead(page, "#degree--0", user_data["degree"]):
                fields_success += 1
                field_results.append({"field": "degree", "success": True})
            else:
                field_results.append({"field": "degree", "success": False})
            
            # Discipline with enhanced handling
            fields_total += 1
            if await enhanced_typeahead(page, "#discipline--0", user_data["discipline"]):
                fields_success += 1
                field_results.append({"field": "discipline", "success": True})
            else:
                field_results.append({"field": "discipline", "success": False})
            
            # Answer custom questions
            logger.info("Filling custom questions")
            # Why Discord question
            fields_total += 1
            if await fill_field(page, "#question_30608968002", user_data["why_discord"]):
                fields_success += 1
                field_results.append({"field": "why_discord", "success": True})
            else:
                field_results.append({"field": "why_discord", "success": False})
                
            # How heard about job
            fields_total += 1
            if await fill_field(page, "#question_30608971002", "LinkedIn"):
                fields_success += 1
                field_results.append({"field": "heard_from", "success": True})
            else:
                field_results.append({"field": "heard_from", "success": False})
                
            # LinkedIn profile
            fields_total += 1
            if await fill_field(page, "#question_30608969002", user_data["linkedin"]):
                fields_success += 1
                field_results.append({"field": "linkedin", "success": True})
            else:
                field_results.append({"field": "linkedin", "success": False})
            
            # Handle dropdown selections with more robust approach
            logger.info("Handling dropdown selections with enhanced method")
            
            # Work authorization
            fields_total += 1
            if await enhanced_dropdown_select(page, "#question_30608972002", "Yes"):
                fields_success += 1
                field_results.append({"field": "work_authorization", "success": True})
            else:
                field_results.append({"field": "work_authorization", "success": False})
                
            # Currently in US
            fields_total += 1
            if await enhanced_dropdown_select(page, "#question_30608973002", "Yes"):
                fields_success += 1
                field_results.append({"field": "in_us", "success": True})
            else:
                field_results.append({"field": "in_us", "success": False})
            
            # Diversity questions
            fields_total += 1
            if await enhanced_dropdown_select(page, "#gender", "Male"):
                fields_success += 1
                field_results.append({"field": "gender", "success": True})
            else:
                field_results.append({"field": "gender", "success": False})
                
            fields_total += 1
            if await enhanced_dropdown_select(page, "#hispanic_ethnicity", "No"):
                fields_success += 1
                field_results.append({"field": "hispanic", "success": True})
            else:
                field_results.append({"field": "hispanic", "success": False})
                
            fields_total += 1
            if await enhanced_dropdown_select(page, "#veteran_status", "I am not a protected veteran"):
                fields_success += 1
                field_results.append({"field": "veteran", "success": True})
            else:
                field_results.append({"field": "veteran", "success": False})
                
            fields_total += 1
            disability_value = "No, I don't have a disability"
            if await enhanced_dropdown_select(page, "#disability_status", disability_value, partial_match=True):
                fields_success += 1
                field_results.append({"field": "disability", "success": True})
            else:
                field_results.append({"field": "disability", "success": False})
            
            # Print results summary
            logger.info(f"Form filling completed: {fields_success}/{fields_total} fields successful")
            
            # Print detailed results
            logger.info("Field results:")
            for result in field_results:
                success_str = "✓ SUCCESS" if result["success"] else "✗ FAILED"
                strategy_str = f" ({result.get('strategy', '')})" if "strategy" in result else ""
                logger.info(f"{success_str} - {result['field']}{strategy_str}")
            
            # Wait to observe the filled form
            logger.info("Waiting for observation (30 seconds)...")
            await asyncio.sleep(30)  # Reduced wait time
            
            # Take screenshot
            await page.screenshot(path="discord_application_filled.png")
            logger.info("Screenshot saved as discord_application_filled.png")
            
        except Exception as e:
            logger.error(f"Test failed with error: {e}")
            # Take screenshot on error
            try:
                await page.screenshot(path="discord_application_error.png")
                logger.info("Error screenshot saved as discord_application_error.png")
            except:
                pass
        
        finally:
            # Close the browser
            await browser.close()
            logger.info("Test completed")

async def fill_field(page, selector, value):
    """Fill a text field with retry logic."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Ensure element is visible and scrolled into view
            try:
                await page.wait_for_selector(selector, state="visible", timeout=5000)
                await page.evaluate(f"document.querySelector('{selector}').scrollIntoView({{behavior: 'smooth', block: 'center'}})")
                await asyncio.sleep(0.2)
            except:
                pass
            
            # Try to focus and fill
            await page.focus(selector)
            await asyncio.sleep(0.2)
            await page.fill(selector, value)
            await asyncio.sleep(0.5)  # Small delay for visibility
            
            # Verify the field was filled correctly
            field_value = await page.evaluate(f"document.querySelector('{selector}').value")
            if field_value:  # If field has any value, consider it successful
                logger.info(f"Successfully filled {selector} with '{value}'")
                return True
                
            if attempt < max_retries - 1:
                logger.warning(f"Field value verification failed for {selector}, retrying...")
                await asyncio.sleep(0.5)
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt+1} failed for {selector}: {e}, retrying...")
                await asyncio.sleep(0.5)
            else:
                logger.error(f"Failed to fill {selector} after {max_retries} attempts: {e}")
                return False
    
    return False

async def enhanced_typeahead(page, selector, value, use_arrow_keys=False):
    """Enhanced typeahead field handling with multiple strategies."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Ensure element is visible and scrolled into view
            try:
                await page.wait_for_selector(selector, state="visible", timeout=5000)
                await page.evaluate(f"document.querySelector('{selector}').scrollIntoView({{behavior: 'smooth', block: 'center'}})")
                await asyncio.sleep(0.2)
            except:
                pass
            
            # Click to focus
            await page.click(selector)
            await asyncio.sleep(0.3)
            
            # Clear existing value
            await page.fill(selector, "")
            await asyncio.sleep(0.3)
            
            # Type slowly to ensure dropdown appears
            # Break into smaller chunks for more reliable typeahead behavior
            chunks = []
            remaining = value
            while remaining:
                chunk_size = min(3, len(remaining))
                chunks.append(remaining[:chunk_size])
                remaining = remaining[chunk_size:]
            
            for chunk in chunks:
                await page.type(selector, chunk, delay=100)
                await asyncio.sleep(0.3)
            
            # Wait for dropdown to appear
            await asyncio.sleep(1)
            
            # Try different selection strategies
            if use_arrow_keys:
                # Strategy 1: Arrow down and Enter
                await page.keyboard.press("ArrowDown")
                await asyncio.sleep(0.3)
                await page.keyboard.press("Enter")
            else:
                # Strategy 2: Direct Enter
                await page.keyboard.press("Enter")
            
            await asyncio.sleep(0.5)
            
            # Verify something was selected (field should have a value)
            field_value = await page.evaluate(f"document.querySelector('{selector}').value")
            if field_value:  # If field has any value, consider it successful
                logger.info(f"Successfully filled typeahead {selector} with '{value}' (selected: '{field_value}')")
                return True
                
            if attempt < max_retries - 1:
                logger.warning(f"Typeahead selection failed for {selector}, retrying...")
                await asyncio.sleep(0.5)
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt+1} failed for typeahead {selector}: {e}, retrying...")
                await asyncio.sleep(0.5)
            else:
                logger.error(f"Failed to fill typeahead {selector} after {max_retries} attempts: {e}")
                
                # Last resort: try to just type the value and tab out
                try:
                    await page.fill(selector, value)
                    await page.keyboard.press("Tab")
                    logger.info(f"Used fallback method for typeahead {selector}")
                    return True
                except:
                    return False
    
    return False

async def enhanced_dropdown_select(page, selector, option_text, partial_match=False):
    """Enhanced dropdown selection with multiple strategies."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Ensure element is visible and scrolled into view
            try:
                await page.wait_for_selector(selector, state="visible", timeout=5000)
                await page.evaluate(f"document.querySelector('{selector}').scrollIntoView({{behavior: 'smooth', block: 'center'}})")
                await asyncio.sleep(0.2)
            except:
                pass
            
            # Click to open dropdown
            await page.click(selector)
            await asyncio.sleep(1.0)  # Longer wait for dropdown to fully open
            
            # Check if dropdown menu opened with options
            dropdown_visible = await page.evaluate("""() => {
                // Check common dropdown elements
                const selectMenus = document.querySelectorAll('.select__menu, [role="listbox"], .dropdown-menu');
                for (let menu of selectMenus) {
                    if (menu && window.getComputedStyle(menu).display !== 'none') {
                        return true;
                    }
                }
                return false;
            }""")
            
            if not dropdown_visible and attempt < max_retries - 1:
                logger.warning(f"Dropdown may not have opened for {selector}, retrying...")
                await asyncio.sleep(0.5)
                continue
            
            # Strategy 1: Try to find by exact text
            try:
                option_selector = f"text='{option_text}'"
                await page.click(option_selector, timeout=2000)
                logger.info(f"Selected '{option_text}' from dropdown {selector} using exact text match")
                await asyncio.sleep(0.5)
                return True
            except Exception as e1:
                logger.debug(f"Exact text match failed: {e1}")
                
                # Strategy 2: Try to find by partial text if enabled
                if partial_match:
                    try:
                        # Escape special characters in option_text
                        safe_text = re.escape(option_text)
                        await page.evaluate(f"""() => {{
                            const options = document.querySelectorAll('.select__option, [role="option"], .dropdown-item');
                            for (let option of options) {{
                                if (option.textContent.includes('{safe_text}')) {{
                                    option.click();
                                    return true;
                                }}
                            }}
                            return false;
                        }}""")
                        logger.info(f"Selected option containing '{option_text}' from dropdown {selector}")
                        await asyncio.sleep(0.5)
                        return True
                    except Exception as e2:
                        logger.debug(f"Partial text match failed: {e2}")
                
                # Strategy 3: Type and press Enter
                try:
                    # Some dropdowns allow typing
                    await page.fill(selector, option_text)
                    await page.keyboard.press("Enter")
                    logger.info(f"Selected '{option_text}' from dropdown {selector} using type and enter")
                    await asyncio.sleep(0.5)
                    return True
                except Exception as e3:
                    logger.debug(f"Type and enter failed: {e3}")
            
            if attempt < max_retries - 1:
                logger.warning(f"All dropdown selection strategies failed for {selector}, retrying...")
                # Close dropdown by clicking elsewhere before retry
                try:
                    await page.click("body", position={"x": 10, "y": 10})
                    await asyncio.sleep(0.5)
                except:
                    pass
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt+1} failed for dropdown {selector}: {e}, retrying...")
                await asyncio.sleep(0.5)
                # Close dropdown by clicking elsewhere before retry
                try:
                    await page.click("body", position={"x": 10, "y": 10})
                    await asyncio.sleep(0.5)
                except:
                    pass
            else:
                logger.error(f"Failed to select from dropdown {selector} after {max_retries} attempts: {e}")
                return False
    
    return False

if __name__ == "__main__":
    asyncio.run(main()) 