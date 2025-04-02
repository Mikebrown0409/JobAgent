"""Job data extraction for the enterprise job application system."""

import logging
from typing import Dict, Any
from playwright.async_api import Page

from enterprise_job_agent.core.browser_manager import BrowserManager

logger = logging.getLogger(__name__)

# Remove analyze_form, assuming form structure is now part of job_data from BrowserManager
# async def analyze_form(page: Page) -> Dict[str, Any]:
#    ...

# Modify to accept browser_manager instance
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
        
        # Extract job details using the provided manager
        job_details = await browser_manager.extract_job_details()
        logger.info(f"Extracted job details: {job_details.get('title', 'N/A')} at {job_details.get('company', 'N/A')}")
        
        # Get current page for form analysis
        page = await browser_manager.get_page()
        
        # Basic form analysis (consider moving to FormAnalyzerAgent later)
        inputs = await page.query_selector_all("input, select, textarea, button")
        form_elements = []
        for elem in inputs:
            try: # Ensure try block exists for each element analysis
                 elem_id = await elem.get_attribute("id") or ""
                 elem_name = await elem.get_attribute("name") or ""
                 aria_label = await elem.get_attribute("aria-label") or ""
                 aria_labelledby = await elem.get_attribute("aria-labelledby") or ""
                 # Generate a simple selector (ID preferred, then name)
                 selector = f"[id='{elem_id}']" if elem_id else (f"[name='{elem_name}']" if elem_name else None)
                 
                 elem_info = {
                    "tag": await elem.evaluate("el => el.tagName.toLowerCase()"),
                    "type": await elem.get_attribute("type") or "",
                    "id": elem_id,
                    "name": elem_name,
                    "aria_label": aria_label,
                    "aria_labelledby": aria_labelledby,
                    "selector": selector
                 }
                 if selector: # Only add elements if we could generate a basic selector
                    form_elements.append(elem_info)
                 else:
                     logger.debug("Skipping element with no ID or name during basic analysis.")
                     
            except Exception as e:
                logger.debug(f"Skipping element during basic form analysis due to error: {e}")

        # Detect iframes
        iframes = await page.query_selector_all("iframe")
        has_iframe = len(iframes) > 0
        if has_iframe:
             logger.info("Detected iframes on the page.")
             for iframe in iframes:
                 try: # Ensure try block exists for each iframe analysis
                     iframe_id = await iframe.get_attribute("id") or ""
                     iframe_name = await iframe.get_attribute("name") or ""
                     iframe_info = {
                        "tag": "iframe",
                        "id": iframe_id,
                        "name": iframe_name,
                        "src": await iframe.get_attribute("src") or "",
                        # Provide a potential identifier for frame_manager
                        "identifier": iframe_name if iframe_name else (iframe_id if iframe_id else None)
                     }
                     form_elements.append(iframe_info)
                 except Exception as e:
                     logger.debug(f"Skipping iframe during basic form analysis due to error: {e}")
        
        form_structure = {
            "elements": form_elements, 
            "element_count": len(form_elements),
            "has_iframe": has_iframe
        }
        logger.info(f"Analyzed form structure with {form_structure.get('element_count', 0)} elements")
        
        # Screenshot path is handled in main
        
        # Return job data
        return {
            "job_details": job_details,
            "form_structure": form_structure,
        }
    except Exception as e:
        logger.error(f"Error extracting job data: {e}")
        return {}
    # No finally block needed as we don't close the passed browser_manager 