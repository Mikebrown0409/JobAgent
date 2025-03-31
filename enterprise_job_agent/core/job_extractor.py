"""Job data extraction for the enterprise job application system."""

import logging
from typing import Dict, Any
from playwright.async_api import Page

from enterprise_job_agent.core.browser_manager import BrowserManager

logger = logging.getLogger(__name__)

async def analyze_form(page: Page) -> Dict[str, Any]:
    """
    Analyze the form structure on the page.
    
    Args:
        page: Playwright page object
        
    Returns:
        Dictionary with form structure information
    """
    logger.info("Analyzing form structure")
    try:
        # Extract form elements
        form_elements = []
        
        # Look for input elements
        inputs = await page.query_selector_all("input, select, textarea")
        
        for input_elem in inputs:
            try:
                # Get element attributes
                input_type = await input_elem.get_attribute("type") or "text"
                input_id = await input_elem.get_attribute("id") or ""
                input_name = await input_elem.get_attribute("name") or ""
                input_class = await input_elem.get_attribute("class") or ""
                placeholder = await input_elem.get_attribute("placeholder") or ""
                required = await input_elem.get_attribute("required") is not None
                
                # Get element tag name
                tag_name = await input_elem.evaluate("el => el.tagName.toLowerCase()")
                
                # Determine label text
                label_text = ""
                
                # Try to find associated label
                if input_id:
                    label = await page.query_selector(f"label[for='{input_id}']")
                    if label:
                        label_text = (await label.text_content() or "").strip()
                
                # If no label found, try using placeholder or nearby text
                if not label_text and placeholder:
                    label_text = placeholder
                
                # Get element selector for future reference
                selector = await input_elem.evaluate("""el => {
                    if (el.id) return `#${el.id}`;
                    if (el.name) return `[name="${el.name}"]`;
                    
                    let classes = Array.from(el.classList).join('.');
                    if (classes) return `.${classes}`;
                    
                    return el.tagName.toLowerCase();
                }""")
                
                # Check if element is visible
                is_visible = await input_elem.is_visible()
                
                # Skip hidden inputs unless they appear to be important
                if input_type == "hidden" and not ("token" in input_name or "key" in input_name):
                    continue
                    
                # Create element info
                element_info = {
                    "type": tag_name,
                    "input_type": input_type,
                    "id": input_id,
                    "name": input_name,
                    "class": input_class,
                    "label": label_text,
                    "placeholder": placeholder,
                    "required": required,
                    "visible": is_visible,
                    "selector": selector
                }
                
                form_elements.append(element_info)
            except Exception as e:
                logger.warning(f"Error analyzing form element: {e}")
        
        # Look for buttons
        buttons = await page.query_selector_all("button, input[type='submit']")
        
        for button in buttons:
            try:
                # Get button attributes
                button_type = await button.get_attribute("type") or "button"
                button_id = await button.get_attribute("id") or ""
                button_name = await button.get_attribute("name") or ""
                button_class = await button.get_attribute("class") or ""
                button_text = (await button.text_content() or "").strip()
                
                if not button_text:
                    button_text = await button.get_attribute("value") or ""
                
                # Get button selector
                selector = await button.evaluate("""el => {
                    if (el.id) return `#${el.id}`;
                    if (el.name) return `[name="${el.name}"]`;
                    
                    let classes = Array.from(el.classList).join('.');
                    if (classes) return `.${classes}`;
                    
                    return el.tagName.toLowerCase();
                }""")
                
                # Create button info
                element_info = {
                    "type": "button",
                    "button_type": button_type,
                    "id": button_id,
                    "name": button_name,
                    "class": button_class,
                    "text": button_text,
                    "selector": selector
                }
                
                form_elements.append(element_info)
            except Exception as e:
                logger.warning(f"Error analyzing button element: {e}")
        
        # Check for iframe forms
        iframes = await page.query_selector_all("iframe")
        
        for iframe in iframes:
            try:
                iframe_url = await iframe.get_attribute("src") or ""
                iframe_id = await iframe.get_attribute("id") or ""
                iframe_name = await iframe.get_attribute("name") or ""
                
                # Create iframe info
                element_info = {
                    "type": "iframe",
                    "id": iframe_id,
                    "name": iframe_name,
                    "src": iframe_url
                }
                
                form_elements.append(element_info)
            except Exception as e:
                logger.warning(f"Error analyzing iframe element: {e}")
        
        # Return form structure
        return {
            "elements": form_elements,
            "element_count": len(form_elements),
            "has_iframe": any(e["type"] == "iframe" for e in form_elements)
        }
    except Exception as e:
        logger.error(f"Error analyzing form: {e}")
        return {
            "elements": [],
            "element_count": 0,
            "has_iframe": False,
            "error": str(e)
        }

async def extract_job_data(url: str, headless: bool = True) -> Dict[str, Any]:
    """
    Extract job data from a job posting URL.
    
    Args:
        url: URL of the job posting
        headless: Whether to run browser in headless mode
        
    Returns:
        Dictionary with job details and form structure
    """
    logger.info(f"Extracting job data from {url}")
    browser_manager = None
    
    try:
        # Initialize browser manager
        browser_manager = BrowserManager(headless=headless)
        
        # Start browser
        if not await browser_manager.start():
            logger.error("Failed to start browser")
            return {}
        
        # Navigate to job URL
        if not await browser_manager.navigate(url):
            logger.error(f"Failed to navigate to {url}")
            return {}
        
        # Extract job details
        job_details = await browser_manager.extract_job_details()
        logger.info(f"Extracted job details: {job_details['title']} at {job_details['company']}")
        
        # Get current page for form analysis
        page = await browser_manager.get_page()
        
        # Analyze form structure
        form_structure = await analyze_form(page)
        logger.info(f"Analyzed form structure with {form_structure.get('element_count', 0)} elements")
        
        # Take screenshot
        screenshot_path = await browser_manager.take_screenshot("job_posting.png")
        logger.info(f"Screenshot saved to {screenshot_path}")
        
        # Return job data
        return {
            "job_details": job_details,
            "form_structure": form_structure,
            "screenshot_path": screenshot_path
        }
    except Exception as e:
        logger.error(f"Error extracting job data: {e}")
        return {}
    finally:
        # Close browser
        if browser_manager:
            await browser_manager.close() 