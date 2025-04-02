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
        
        # Wait for page to be fully loaded
        page = await browser_manager.get_page()
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
            logger.info("Page reached network idle state")
        except Exception as e:
            logger.warning(f"Wait for network idle timed out, continuing: {e}")
        
        # Map all frames if frame manager is available
        if browser_manager.frame_manager:
            await browser_manager.frame_manager.map_all_frames()
            logger.info(f"Mapped {len(browser_manager.frame_manager.frames)} frames")
        
        # Extract job details using the provided manager
        job_details = await browser_manager.extract_job_details()
        logger.info(f"Extracted job details: {job_details.get('title', 'N/A')} at {job_details.get('company', 'N/A')}")
        
        # Get current page for form analysis
        page = await browser_manager.get_page()
        
        # Enhanced form analysis - works better with complex forms
        form_elements = []
        
        # First check if we're already in an application form or need to click "Apply"
        apply_button = None
        try:
            # Look for common apply button patterns
            apply_selectors = [
                "a.apply-button", "button.apply", "a[href*='apply']",
                "button:has-text('Apply')", "a:has-text('Apply')",
                ".jobs-apply-button", "#apply-button"
            ]
            
            for selector in apply_selectors:
                apply_button = page.locator(selector).first
                if await apply_button.count() > 0 and await apply_button.is_visible():
                    logger.info(f"Found apply button with selector: {selector}")
                    # Click apply button
                    try:
                        logger.info("Clicking apply button to load application form")
                        await apply_button.click()
                        # Wait for form to load
                        await page.wait_for_load_state("networkidle", timeout=10000)
                        # Re-map frames if needed
                        if browser_manager.frame_manager:
                            await browser_manager.frame_manager.map_all_frames()
                            logger.info(f"Re-mapped frames after clicking apply: {len(browser_manager.frame_manager.frames)} frames")
                        break
                    except Exception as e:
                        logger.warning(f"Error clicking apply button: {e}")
                        apply_button = None
        except Exception as e:
            logger.debug(f"Error finding apply button: {e}")
        
        # Get all frames to analyze (including main page)
        frames_to_check = {"main": page.main_frame}
        if browser_manager.frame_manager:
            frames_to_check = browser_manager.frame_manager.frames
            
        # Process each frame for form elements
        for frame_id, frame in frames_to_check.items():
            logger.debug(f"Analyzing form elements in frame: {frame_id}")
            try:
                # Wait for frame to be stable
                try:
                    await frame.wait_for_load_state("networkidle", timeout=5000)
                except Exception as frame_wait_error:
                    logger.debug(f"Frame wait error: {frame_wait_error}")
                
                # Enhanced selectors for various input types
                selectors = [
                    "input", "select", "textarea", "button[type='submit']",
                    "[role='textbox']", "[role='combobox']", "[role='button']",
                    ".form-control", ".input-field", "div.dropdown"
                ]
                
                for selector in selectors:
                    elements = await frame.query_selector_all(selector)
                    for elem in elements:
                        try:
                            # Extract core attributes
                            elem_id = await elem.get_attribute("id") or ""
                            elem_name = await elem.get_attribute("name") or ""
                            elem_type = await elem.get_attribute("type") or ""
                            aria_label = await elem.get_attribute("aria-label") or ""
                            aria_labelledby = await elem.get_attribute("aria-labelledby") or ""
                            placeholder = await elem.get_attribute("placeholder") or ""
                            required = await elem.get_attribute("required") is not None
                            
                            # Determine element tag
                            tag_name = await elem.evaluate("el => el.tagName.toLowerCase()")
                            
                            # Try to find associated label
                            label_text = ""
                            
                            # Method 1: Check for aria-labelledby
                            if aria_labelledby:
                                try:
                                    label_elem = await frame.query_selector(f"#{aria_labelledby}")
                                    if label_elem:
                                        label_text = await label_elem.text_content() or ""
                                except Exception:
                                    pass
                            
                            # Method 2: Check for linked label element
                            if elem_id and not label_text:
                                try:
                                    label_elem = await frame.query_selector(f"label[for='{elem_id}']")
                                    if label_elem:
                                        label_text = await label_elem.text_content() or ""
                                except Exception:
                                    pass
                            
                            # Method 3: Check for parent label
                            if not label_text:
                                try:
                                    parent_label = await elem.evaluate("""
                                        el => {
                                            const parent = el.closest('label');
                                            return parent ? parent.textContent : '';
                                        }
                                    """)
                                    if parent_label:
                                        label_text = parent_label
                                except Exception:
                                    pass
                            
                            # Method 4: Check nearby text
                            if not label_text:
                                try:
                                    nearby_text = await elem.evaluate("""
                                        el => {
                                            const prev = el.previousElementSibling;
                                            if (prev && prev.textContent.trim()) return prev.textContent;
                                            
                                            const parent = el.parentElement;
                                            const children = Array.from(parent.childNodes);
                                            for (let i = 0; i < children.length; i++) {
                                                if (children[i] === el && i > 0 && children[i-1].nodeType === 3) {
                                                    return children[i-1].textContent;
                                                }
                                            }
                                            return '';
                                        }
                                    """)
                                    if nearby_text:
                                        label_text = nearby_text
                                except Exception:
                                    pass
                            
                            # Fallback to aria-label or placeholder
                            if not label_text:
                                label_text = aria_label or placeholder
                            
                            # Generate a selector (ID preferred, then name)
                            selector = None
                            if elem_id:
                                selector = f"[id='{elem_id}']"
                            elif elem_name:
                                selector = f"[name='{elem_name}']"
                            else:
                                # Try to create a unique CSS selector
                                try:
                                    selector = await elem.evaluate("""
                                        el => {
                                            let path = '';
                                            while (el) {
                                                let name = el.localName;
                                                if (!name) break;
                                                
                                                if (el.id) {
                                                    return "#" + el.id + path;
                                                }
                                                
                                                let sibling = el, index = 1;
                                                while (sibling = sibling.previousElementSibling) {
                                                    if (sibling.localName === name) index++;
                                                }
                                                
                                                if (index !== 1) name += `:nth-of-type(${index})`;
                                                path = `> ${name}${path}`;
                                                el = el.parentElement;
                                            }
                                            return path.substring(2);
                                        }
                                    """)
                                except Exception:
                                    selector = None
                            
                            # Skip elements without a way to select them
                            if not selector:
                                continue
                            
                            # Get additional attributes for select elements
                            options = []
                            if tag_name == "select":
                                try:
                                    options = await elem.evaluate("""
                                        el => Array.from(el.options).map(o => ({
                                            value: o.value,
                                            text: o.text,
                                            selected: o.selected
                                        }))
                                    """)
                                except Exception:
                                    pass
                            
                            # Check if element is visible (approximation)
                            is_visible = False
                            try:
                                is_visible = await elem.is_visible()
                            except Exception:
                                # If we can't determine visibility, assume it might be visible
                                is_visible = True
                                
                            # Add the element info
                            label_text = label_text.strip() if label_text else ""
                            
                            # Create element info with frame context
                            elem_info = {
                                "tag": tag_name,
                                "type": elem_type or tag_name,
                                "id": elem_id,
                                "name": elem_name,
                                "label": label_text,
                                "aria_label": aria_label,
                                "aria_labelledby": aria_labelledby,
                                "placeholder": placeholder,
                                "required": required,
                                "selector": selector,
                                "options": options,
                                "is_visible": is_visible,
                                "frame_id": frame_id
                            }
                            
                            # Filter out non-essential elements like hidden fields, buttons, etc.
                            if tag_name == "input" and elem_type in ["hidden", "submit", "button", "reset", "image"]:
                                continue
                                
                            form_elements.append(elem_info)
                        except Exception as elem_error:
                            logger.debug(f"Error processing element in frame {frame_id}: {elem_error}")
            except Exception as frame_error:
                logger.warning(f"Error analyzing frame {frame_id}: {frame_error}")
        
        # Detect iframes separately
        iframes = await page.query_selector_all("iframe")
        has_iframe = len(iframes) > 0
        if has_iframe:
             logger.info(f"Detected {len(iframes)} iframes on the page.")
             for iframe in iframes:
                 try:
                     iframe_id = await iframe.get_attribute("id") or ""
                     iframe_name = await iframe.get_attribute("name") or ""
                     iframe_info = {
                        "tag": "iframe",
                        "id": iframe_id,
                        "name": iframe_name,
                        "src": await iframe.get_attribute("src") or "",
                        "identifier": iframe_name if iframe_name else (iframe_id if iframe_id else None)
                     }
                     # Add iframe as a form element for reference
                     form_elements.append(iframe_info)
                 except Exception as e:
                     logger.debug(f"Skipping iframe during analysis due to error: {e}")
        
        # Clean and organize form elements
        cleaned_form_elements = []
        seen_selectors = set()
        
        for elem in form_elements:
            # Skip duplicates based on selector
            if elem.get("selector") in seen_selectors:
                continue
                
            # Add selector to seen set if it exists
            if elem.get("selector"):
                seen_selectors.add(elem.get("selector"))
                
            # Clean up the element - remove None values and empty strings
            cleaned_elem = {k: v for k, v in elem.items() if v is not None and v != ""}
            
            # Add to cleaned list
            cleaned_form_elements.append(cleaned_elem)
        
        form_structure = {
            "elements": cleaned_form_elements, 
            "element_count": len(cleaned_form_elements),
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