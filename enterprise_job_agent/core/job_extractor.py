"""Job data extraction for the enterprise job application system."""

import logging
from typing import Dict, Any, List, Optional, Tuple
from playwright.async_api import Page, ElementHandle

from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.agents.form_analyzer_agent import FormAnalyzerAgent

logger = logging.getLogger(__name__)

async def extract_form_elements(page: Page) -> List[Dict[str, Any]]:
    """Extract form elements from the page."""
    form_elements = []
    
    # Common form element selectors
    selectors = [
        "input", "select", "textarea", "button[type='submit']",
        "input[type='submit']", "button:has-text('Submit')"
    ]
    
    for selector in selectors:
        try:
            elements = await page.query_selector_all(selector)
            for element in elements:
                try:
                    # Get basic element attributes
                    element_type = await element.get_attribute("type") or selector.split("[")[0]
                    element_id = await element.get_attribute("id")
                    element_name = await element.get_attribute("name")
                    element_required = await element.get_attribute("required") is not None
                    element_placeholder = await element.get_attribute("placeholder")
                    
                    # Get label text if available
                    label_text = None
                    if element_id:
                        label = await page.query_selector(f"label[for='{element_id}']")
                        if label:
                            label_text = await label.text_content()
                    
                    # Create element info dictionary
                    element_info = {
                        "type": element_type,
                        "id": element_id,
                        "name": element_name,
                        "required": element_required,
                        "placeholder": element_placeholder,
                        "label": label_text,
                        "selector": selector
                    }
                    
                    # Add validation attributes if present
                    for attr in ["pattern", "minlength", "maxlength", "min", "max"]:
                        value = await element.get_attribute(attr)
                        if value:
                            element_info[attr] = value
                    
                    # Add options for select elements
                    if selector == "select":
                        options = []
                        option_elements = await element.query_selector_all("option")
                        for option in option_elements:
                            value = await option.get_attribute("value")
                            text = await option.text_content()
                            options.append({"value": value, "text": text})
                        element_info["options"] = options
                    
                    form_elements.append(element_info)
                except Exception as e:
                    logger.debug(f"Error extracting element info: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Error with selector {selector}: {e}")
            continue
    
    return form_elements

async def find_and_click_apply_button(page: Page, browser_manager: BrowserManager) -> bool:
    """Find and click the apply button if present."""
    apply_selectors = [
        "a.apply-button", "button.apply", "a[href*='apply']",
        "button:has-text('Apply')", "a:has-text('Apply')",
        ".jobs-apply-button", "#apply-button"
    ]
    
    for selector in apply_selectors:
        try:
            apply_button = await page.query_selector(selector)
            if apply_button and await apply_button.is_visible():
                logger.info(f"Found apply button with selector: {selector}")
                try:
                    logger.info("Clicking apply button to load application form")
                    await apply_button.click()
                    # Wait for form to load
                    await page.wait_for_load_state("networkidle", timeout=10000)
                    # Re-map frames if needed
                    if browser_manager.frame_manager:
                        await browser_manager.frame_manager.map_all_frames()
                        logger.info(f"Re-mapped frames after clicking apply: {len(browser_manager.frame_manager.frames)} frames")
                    return True
                except Exception as e:
                    logger.warning(f"Error clicking apply button: {e}")
        except Exception as e:
            logger.debug(f"Error checking selector {selector}: {e}")
            continue
    
    return False

async def extract_job_data(url: str, browser_manager: BrowserManager) -> Dict[str, Any]:
    """
    Extract job data from a job posting URL using a provided BrowserManager instance.
    
    Args:
        url: URL of the job posting
        browser_manager: An active BrowserManager instance.
        
    Returns:
        Dictionary with job details and form structure
    """
    logger.info(f"Extracting job data from {url} using provided browser manager")
    
    try:
        # Use the provided browser manager
        if not browser_manager or not browser_manager.page:
            logger.error("Provided BrowserManager is invalid or not started.")
            return {}

        # Navigate to job URL using the provided manager
        if not await browser_manager.navigate(url):
            logger.error(f"Failed to navigate to {url}")
            return {}
        
        # Wait for page to be fully loaded
        page = browser_manager.page
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
            logger.info("Page reached network idle state")
        except Exception as e:
            logger.warning(f"Wait for network idle timed out, continuing: {e}")
        
        # Map all frames if frame manager is available
        if browser_manager.frame_manager:
            await browser_manager.frame_manager.map_all_frames()
            logger.info(f"Mapped {len(browser_manager.frame_manager.frames)} frames")
        
        # Start job details extraction stage
        if browser_manager.diagnostics_manager:
            browser_manager.diagnostics_manager.start_stage("job_details_extraction")
            
        try:
            # Extract job details first
            job_details = await extract_job_details(page)
            
            # Log success
            title = job_details.get("title", "Unknown Position")
            company = job_details.get("company", "Unknown Company")
            log_msg = f"Extracted job details: {title} at {company}"
            logger.info(log_msg)
            
            # End job details extraction stage successfully
            if browser_manager.diagnostics_manager:
                browser_manager.diagnostics_manager.end_stage(success=True, details=job_details)
            
            # Try to find and click apply button
            clicked_apply = await find_and_click_apply_button(page, browser_manager)
            if clicked_apply:
                logger.info("Successfully clicked apply button and loaded application form")
                
            # Extract form elements
            form_elements = await extract_form_elements(page)
            logger.info(f"Extracted {len(form_elements)} form elements")
            
            # Return combined job details and form elements
            return {
                "job_details": job_details,
                "form_elements": form_elements,
                "clicked_apply": clicked_apply
            }
            
        except Exception as e:
            if browser_manager.diagnostics_manager:
                browser_manager.diagnostics_manager.end_stage(success=False, error=str(e))
            raise
            
    except Exception as e:
        logger.error(f"Error extracting job data: {e}")
        raise

async def extract_job_details(page: Page) -> Dict[str, Any]:
    """Extract job details from the page."""
    # Common selectors for job details
    selectors = {
        "title": [
            "h1.job-title", "h1.posting-headline", ".job-title",
            "h1:has-text('Software')", "h1:has-text('Engineer')",
            "[data-test='job-title']", ".posting-headline"
        ],
        "company": [
            ".company-name", ".employer-name", "[data-test='company-name']",
            ".posting-categories"
        ],
        "location": [
            ".location", ".job-location", "[data-test='location']",
            ".posting-categories"
        ],
        "description": [
            ".job-description", ".description", "[data-test='job-description']",
            "#job-description", ".posting-description"
        ]
    }
    
    job_details = {}
    
    # Extract text for each field using selectors
    for field, field_selectors in selectors.items():
        for selector in field_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    if text and text.strip():
                        job_details[field] = text.strip()
                        break
            except Exception as e:
                logger.debug(f"Error extracting {field} with selector {selector}: {e}")
    
    # If no title found, try to get it from page title
    if "title" not in job_details:
        try:
            title = await page.title()
            if title:
                # Clean up title - remove company name and common suffixes
                title = title.split(" | ")[0].split(" at ")[0].strip()
                job_details["title"] = title
        except Exception as e:
            logger.debug(f"Error extracting title from page title: {e}")
    
    # If no company found, try to get it from URL
    if "company" not in job_details:
        try:
            url = page.url
            # Extract company from URL (e.g., greenhouse.io/company/...)
            company = url.split("/")[3].replace("-", " ").title()
            job_details["company"] = company
        except Exception as e:
            logger.debug(f"Error extracting company from URL: {e}")
    
    # Ensure we have at least a title
    if not job_details.get("title"):
        job_details["title"] = "Unknown Position"
    
    # Ensure we have a company
    if not job_details.get("company"):
        job_details["company"] = "Unknown Company"
    
    # Ensure we have a location
    if not job_details.get("location"):
        job_details["location"] = "Location Not Specified"
    
    # Ensure we have a description
    if not job_details.get("description"):
        job_details["description"] = "No description available"
    
    return job_details 