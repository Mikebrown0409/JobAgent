#!/usr/bin/env python3
"""
Integration test for typeahead field handling on Remote.com job application.
Specifically tests the ability to correctly handle school, degree, and discipline fields.
"""

import os
import sys
import logging
import asyncio
import time
import pytest
from pathlib import Path

# Add parent directory to module search path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.frame_manager import AdvancedFrameManager
from enterprise_job_agent.core.action_executor import ActionExecutor, ActionContext
from enterprise_job_agent.tools.element_selector import ElementSelector
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test URL for Remote.com job application
TEST_URL = "https://job-boards.greenhouse.io/discord/jobs/7845336002"

async def take_screenshot(page, filename):
    """Take a screenshot and save it in the project root"""
    screenshot_path = Path(__file__).parents[3] / filename
    await page.screenshot(path=str(screenshot_path))
    logger.info(f"Took screenshot of page at {screenshot_path}")
    return screenshot_path

async def test_remote_typeahead_fields():
    """Tests typeahead field handling on Remote.com job application."""
    # Initialize browser
    browser_manager = BrowserManager(visible=True)
    
    try:
        # Initialize browser and navigate to the page
        await browser_manager.initialize()
        await browser_manager.navigate(TEST_URL)
        await asyncio.sleep(3)  # Allow page to load fully
        
        # Get tools from browser manager
        element_selector = browser_manager.element_selector
        form_interaction = browser_manager.form_interaction
        
        # Create action executor
        action_executor = ActionExecutor(
            browser_manager=browser_manager,
            form_interaction=form_interaction,
            element_selector=element_selector,
            test_mode=False
        )
        
        logger.info("Starting Remote.com typeahead test...")
        
        # Fill standard fields first to get to the education section
        logger.info("Filling standard fields first...")
        
        # Create ActionContext objects for basic fields
        first_name_context = ActionContext(
            field_id="#first_name",
            field_type="text",
            field_value="Alex",
            field_name="first name"
        )
        await action_executor.execute_action(first_name_context)
        
        last_name_context = ActionContext(
            field_id="#last_name",
            field_type="text",
            field_value="Chen",
            field_name="last name"
        )
        await action_executor.execute_action(last_name_context)
        
        email_context = ActionContext(
            field_id="#email",
            field_type="text",
            field_value="alex.chen@example.com",
            field_name="email"
        )
        await action_executor.execute_action(email_context)
        
        phone_context = ActionContext(
            field_id="#phone",
            field_type="text",
            field_value="555-123-4567",
            field_name="phone"
        )
        await action_executor.execute_action(phone_context)
        
        # Test typeahead field handling
        logger.info("Testing typeahead field handling...")
        
        # Find and test location typeahead field
        location_field = None
        location_selector = None
        for selector in ["#location", "input[name='location']", "input[id*='location']"]:
            try:
                location_field = await element_selector.find_element(selector)
                if location_field:
                    logger.info(f"Found location field with selector: {selector}")
                    location_selector = selector
                    break
            except Exception:
                pass
        
        if location_field and location_selector:
            logger.info("Testing location typeahead field...")
            start_time = time.time()
            
            location_context = ActionContext(
                field_id=location_selector,
                field_type="typeahead",
                field_value="San Francisco, CA",
                field_name="location"
            )
            result = await action_executor.execute_action(location_context)
            
            # Verify the text in the field
            if result:
                actual_text = await browser_manager.page.locator(location_selector).input_value()
                logger.info(f"Text actually in location field: '{actual_text}'")
            
            duration = time.time() - start_time
            logger.info(f"location field completed in {duration:.2f} seconds with success: {bool(result)}")
        
        # Test school typeahead field
        logger.info("Testing school typeahead field...")
        
        # Find school field and analyze its properties
        school_field = await element_selector.find_element("[id*='school']")
        if school_field:
            school_info = await browser_manager.page.evaluate("""() => {
                const element = document.querySelector("[id*='school']");
                if (!element) return null;
                
                return {
                    tag_name: element.tagName.toLowerCase(),
                    attributes: [...element.attributes].reduce((obj, attr) => {
                        obj[attr.name] = attr.value;
                        return obj;
                    }, {}),
                    classes: [...element.classList],
                    selector: element.id ? `#${element.id}` : `[id*='school']`
                };
            }""")
            
            logger.info(f"School field info: {school_info}")
            
            # Check for container to determine if it's a React Select
            container_info = await browser_manager.page.evaluate("""() => {
                const element = document.querySelector("[id*='school']");
                if (!element) return null;
                
                // Look for parent container
                const container = element.closest('.select__input-container') || 
                                element.closest('.css-1hwfws3') ||
                                element.closest('.react-select__value-container');
                
                if (container) {
                    return {
                        class: container.className,
                        id: container.id || '',
                        role: container.getAttribute('role')
                    };
                }
                return null;
            }""")
            
            logger.info(f"School field container: {container_info}")
            
            # Click to show dropdown options
            await browser_manager.page.locator(school_info['selector']).click()
            await asyncio.sleep(0.5)
            
            # Take screenshot of dropdown
            await take_screenshot(browser_manager.page, "remote_school_dropdown.png")
            
            # Get dropdown options
            dropdown_options = await browser_manager.page.evaluate("""() => {
                const options = Array.from(document.querySelectorAll('.select__option, .react-select__option, [class*="selectOption"], [role="option"]'))
                    .map(opt => opt.textContent.trim());
                return options.length ? options : ['No options'];
            }""")
            
            logger.info(f"Dropdown options for school field: {dropdown_options[:10]}")
            
            # Execute typeahead for school
            start_time = time.time()
            
            school_context = ActionContext(
                field_id=school_info['selector'],
                field_type="typeahead",
                field_value="University of California, Berkeley",
                field_name="school"
            )
            result = await action_executor.execute_action(school_context)
            
            # Verify what was actually filled in the field
            actual_text = await browser_manager.page.locator(school_info['selector']).input_value()
            logger.info(f"Text actually in school field: '{actual_text}'")
            
            duration = time.time() - start_time
            logger.info(f"school field completed in {duration:.2f} seconds with success: {bool(result)}")
        
        # Test degree typeahead field
        logger.info("Testing degree typeahead field...")
        
        # Check for degree options first
        degree_options = await browser_manager.page.evaluate("""() => {
            // Find and click the dropdown to open it
            const degreeField = document.querySelector("[id*='degree']");
            if (degreeField) {
                degreeField.click();
                // Wait a bit for the dropdown to open
                return new Promise(resolve => {
                    setTimeout(() => {
                        const options = Array.from(document.querySelectorAll('.select__option, .react-select__option, [class*="selectOption"], [role="option"]'))
                            .map(opt => opt.textContent.trim());
                        resolve(options.length ? options : ['No options']);
                    }, 500);
                });
            }
            return ['No degree field found'];
        }""")
        
        logger.info(f"Available degree options: {degree_options[:10]}")
        
        # Test degree typeahead field
        logger.info("Testing degree typeahead field...")
        
        degree_field = await element_selector.find_element("[id*='degree']")
        if degree_field:
            start_time = time.time()
            
            degree_context = ActionContext(
                field_id="input[id*='degree']",
                field_type="typeahead",
                field_value="Bachelor of Science",
                field_name="degree"
            )
            result = await action_executor.execute_action(degree_context)
            
            # Verify what was filled in the field
            actual_text = await browser_manager.page.locator("input[id*='degree']").input_value()
            logger.info(f"Text actually in degree field: '{actual_text}'")
            
            duration = time.time() - start_time
            logger.info(f"degree field completed in {duration:.2f} seconds with success: {bool(result)}")
        
        # Test discipline typeahead field
        logger.info("Testing discipline typeahead field...")
        
        # Check for discipline options
        discipline_options = await browser_manager.page.evaluate("""() => {
            // Find and click the dropdown to open it
            const disciplineField = document.querySelector("[id*='discipline'], [id*='major'], [id*='field']");
            if (disciplineField) {
                disciplineField.click();
                // Wait a bit for the dropdown to open
                return new Promise(resolve => {
                    setTimeout(() => {
                        const options = Array.from(document.querySelectorAll('.select__option, .react-select__option, [class*="selectOption"], [role="option"]'))
                            .map(opt => opt.textContent.trim());
                        resolve(options.length ? options : ['No options']);
                    }, 500);
                });
            }
            return ['No discipline field found'];
        }""")
        
        logger.info(f"Available discipline options: {discipline_options[:10]}")
        
        # Test discipline typeahead field
        logger.info("Testing discipline typeahead field...")
        
        discipline_field = await element_selector.find_element("input[id*='discipline'], input[id*='major'], input[id*='field']")
        if discipline_field:
            discipline_selector = await browser_manager.page.evaluate("""() => {
                const el = document.querySelector("input[id*='discipline']") || 
                          document.querySelector("input[id*='major']") || 
                          document.querySelector("input[id*='field']");
                return el ? (el.id ? `#${el.id}` : el.outerHTML.substring(0, 100)) : null;
            }""")
            
            if discipline_selector:
                start_time = time.time()
                
                discipline_context = ActionContext(
                    field_id=discipline_selector,
                    field_type="typeahead",
                    field_value="Computer Science",
                    field_name="discipline"
                )
                result = await action_executor.execute_action(discipline_context)
                
                # Verify what was filled in the field
                try:
                    actual_text = await browser_manager.page.locator(discipline_selector).input_value()
                    logger.info(f"Text actually in discipline field: '{actual_text}'")
                except Exception as e:
                    logger.warning(f"Could not get discipline field value: {e}")
                
                duration = time.time() - start_time
                logger.info(f"discipline field completed in {duration:.2f} seconds with success: {bool(result)}")
        
        # Print test results
        logger.info("\n===== Remote.com Typeahead Test Results =====")
        logger.info(f"Location: {bool(location_field)}")
        logger.info(f"School: {bool(school_field)}")
        logger.info(f"Degree: {bool(degree_field)}")
        logger.info(f"Discipline: {bool(discipline_field)}")
        
        logger.info("Test completed!")
        
        # Take a final screenshot
        await take_screenshot(browser_manager.page, "remote_application_filled.png")
        
    finally:
        # Clean up
        await browser_manager.close()

if __name__ == "__main__":
    asyncio.run(test_remote_typeahead_fields()) 