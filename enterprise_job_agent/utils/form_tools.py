"""Tools for working with forms in job applications."""

import asyncio
import logging
import os
from typing import Dict, List, Any, Optional, Tuple
from playwright.async_api import async_playwright, Page, Locator, ElementHandle

logger = logging.getLogger(__name__)

async def analyze_form(page: Page) -> Dict[str, Any]:
    """
    Analyze form elements on a page and extract their structure.
    
    Args:
        page: The playwright page object.
        
    Returns:
        Dictionary containing form structure.
    """
    logger.info("Analyzing form structure")
    
    try:
        # Wait for form elements to be visible
        await page.wait_for_load_state("networkidle", timeout=30000)
        
        # Extract all form elements
        form_elements = []
        
        # Focus on common input types
        selectors = [
            "input:not([type='hidden'])",
            "textarea",
            "select",
            "[role='combobox']",
            "button[type='submit']"
        ]
        
        # Process each selector
        for selector in selectors:
            elements = await page.query_selector_all(selector)
            
            for elem in elements:
                try:
                    # Get element properties
                    tag_name = await elem.evaluate("el => el.tagName.toLowerCase()")
                    elem_type = await elem.evaluate("el => el.type || el.getAttribute('role') || el.tagName.toLowerCase()")
                    elem_id = await elem.evaluate("el => el.id")
                    elem_name = await elem.evaluate("el => el.name")
                    required = await elem.evaluate("el => el.required || el.getAttribute('aria-required') === 'true'")
                    disabled = await elem.evaluate("el => el.disabled || el.getAttribute('aria-disabled') === 'true'")
                    hidden = await elem.evaluate("el => el.hidden || window.getComputedStyle(el).display === 'none' || window.getComputedStyle(el).visibility === 'hidden'")
                    
                    # Skip hidden or disabled elements
                    if hidden or disabled:
                        continue
                    
                    # Get label text using multiple strategies
                    label = await elem.evaluate("""
                        el => {
                            // Check for aria-label
                            if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
                            
                            // Check for associated label
                            if (el.id) {
                                const label = document.querySelector(`label[for="${el.id}"]`);
                                if (label) return label.textContent.trim();
                            }
                            
                            // Check for parent label
                            const parentLabel = el.closest('label');
                            if (parentLabel) {
                                return parentLabel.textContent.replace(el.value || '', '').trim();
                            }
                            
                            // Check for placeholder
                            if (el.placeholder) return el.placeholder;
                            
                            // Check for neighboring label/text
                            const prevSibling = el.previousElementSibling;
                            if (prevSibling && (prevSibling.tagName === 'LABEL' || 
                                prevSibling.tagName === 'SPAN' || prevSibling.tagName === 'DIV')) {
                                return prevSibling.textContent.trim();
                            }
                            
                            // Last resort: find closest text node
                            return el.closest('.form-group, .field-group, .form-field')?.querySelector('label, .label, .field-label')?.textContent?.trim() || 'Unlabeled ' + el.type;
                        }
                    """)
                    
                    # Create selector strategies
                    selectors = {}
                    if elem_id:
                        selectors["id"] = f"#{elem_id}"
                    if elem_name:
                        selectors["name"] = f"[name='{elem_name}']"
                    
                    # Add XPath as a fallback
                    xpath = await elem.evaluate("el => {const xpath = []; let node = el; while (node && node !== document.documentElement) { let sibling = node.previousSibling; let index = 1; while (sibling) { if (sibling.nodeType === 1 && sibling.tagName === node.tagName) { index++; } sibling = sibling.previousSibling; } xpath.unshift(node.tagName.toLowerCase() + (index > 1 ? '[' + index + ']' : '')); node = node.parentNode; } return '/' + xpath.join('/')}")
                    selectors["xpath"] = xpath
                    
                    # Extract options for select elements
                    options = []
                    if tag_name == "select":
                        options = await elem.evaluate("el => Array.from(el.options).map(opt => opt.text.trim())")
                    
                    # Determine element's section
                    section_id = await elem.evaluate("""
                        el => {
                            const fieldset = el.closest('fieldset');
                            if (fieldset && fieldset.id) return fieldset.id;
                            
                            const section = el.closest('section, div[role="group"]');
                            if (section && section.id) return section.id;
                            
                            return null;
                        }
                    """)
                    
                    # Create element entry
                    element = {
                        "id": elem_id or f"element_{len(form_elements)}",
                        "name": elem_name or "",
                        "label": label,
                        "type": elem_type,
                        "role": await elem.evaluate("el => el.getAttribute('role') || ''"),
                        "required": required,
                        "disabled": disabled,
                        "hidden": hidden,
                        "value": await elem.evaluate("el => el.value || ''"),
                        "placeholder": await elem.evaluate("el => el.placeholder || ''"),
                        "options": options,
                        "max_length": await elem.evaluate("el => el.getAttribute('maxlength')"),
                        "min": await elem.evaluate("el => el.getAttribute('min')"),
                        "max": await elem.evaluate("el => el.getAttribute('max')"),
                        "pattern": await elem.evaluate("el => el.getAttribute('pattern')"),
                        "section_id": section_id,
                        "selectors": selectors
                    }
                    
                    form_elements.append(element)
                    
                except Exception as e:
                    logger.warning(f"Error processing form element: {e}")
        
        # Extract form sections
        sections = []
        section_elements = await page.query_selector_all("fieldset, .form-section, .application-section, div[role='group']")
        
        for i, section in enumerate(section_elements):
            try:
                section_name = await section.evaluate("""
                    el => {
                        const legend = el.querySelector('legend');
                        const heading = el.querySelector('h1, h2, h3, h4, h5, h6');
                        const label = el.querySelector('label');
                        return (legend?.textContent || heading?.textContent || label?.textContent || '').trim();
                    }
                """)
                
                section_id = await section.evaluate("el => el.id") or f"section_{i}"
                
                if section_name:
                    sections.append({
                        "id": section_id,
                        "name": section_name,
                        "elements": []
                    })
            except Exception as e:
                logger.warning(f"Error processing form section: {e}")
        
        # Identify form navigation (submit buttons, etc.)
        navigation = {
            "buttons": [],
            "multi_page": False
        }
        
        submit_buttons = await page.query_selector_all("button[type='submit'], input[type='submit'], button:has-text('Apply'), button:has-text('Submit')")
        
        for i, button in enumerate(submit_buttons):
            try:
                button_text = await button.text_content()
                button_type = await button.evaluate("el => el.type || 'button'")
                
                navigation["buttons"].append({
                    "id": f"button_{i}",
                    "label": button_text.strip() or "Unlabeled submit",
                    "type": button_type,
                    "selector": f"button:has-text(\"{button_text.strip()}\")"
                })
            except Exception as e:
                logger.warning(f"Error processing submit button: {e}")
        
        # Check if form is multi-page
        pagination_elements = await page.query_selector_all(".pagination, .page-navigation, button:has-text('Next'), button:has-text('Previous')")
        navigation["multi_page"] = len(pagination_elements) > 0
        
        # Get page URL and title
        page_url = page.url
        page_title = await page.title()
        
        # Construct the final form structure
        form_structure = {
            "form_elements": form_elements,
            "sections": sections,
            "navigation": navigation,
            "page_url": page_url,
            "page_title": page_title
        }
        
        return form_structure
        
    except Exception as e:
        logger.error(f"Error analyzing form: {e}")
        return {
            "error": str(e),
            "form_elements": []
        }

async def fill_text_field(page: Page, selector: str, value: str, frame_id: str = None) -> bool:
    """
    Fill a text field with a value.
    
    Args:
        page: Playwright page object
        selector: Selector for the element
        value: Value to fill
        frame_id: Optional frame ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the target frame
        frame = page.frame(name=frame_id) if frame_id else page.main_frame
        if not frame:
            logger.error(f"Frame {frame_id} not found")
            return False
            
        # Clear the field first
        await frame.fill(selector, "")
        
        # Type the value with human-like delays
        await frame.type(selector, value, delay=100)
        
        logger.debug(f"Filled text field {selector} with '{value}'")
        return True
    except Exception as e:
        logger.error(f"Error filling text field {selector}: {e}")
        return False

async def select_option(page: Page, selector: str, value: str, frame_id: str = None) -> bool:
    """
    Select an option from a dropdown.
    
    Args:
        page: Playwright page object
        selector: Selector for the element
        value: Value or label to select
        frame_id: Optional frame ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the target frame
        frame = page.frame(name=frame_id) if frame_id else page.main_frame
        if not frame:
            logger.error(f"Frame {frame_id} not found")
            return False
            
        # Try to select by value first
        try:
            await frame.select_option(selector, value=value)
            logger.debug(f"Selected option with value '{value}' from {selector}")
            return True
        except Exception:
            # If that fails, try by label
            try:
                await frame.select_option(selector, label=value)
                logger.debug(f"Selected option with label '{value}' from {selector}")
                return True
            except Exception as e:
                logger.error(f"Error selecting option '{value}' from {selector}: {e}")
                return False
    except Exception as e:
        logger.error(f"Error with select operation on {selector}: {e}")
        return False

async def click_element(page: Page, selector: str, frame_id: str = None) -> bool:
    """
    Click an element.
    
    Args:
        page: Playwright page object
        selector: Selector for the element
        frame_id: Optional frame ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the target frame
        frame = page.frame(name=frame_id) if frame_id else page.main_frame
        if not frame:
            logger.error(f"Frame {frame_id} not found")
            return False
            
        # Make sure the element is visible
        await frame.wait_for_selector(selector, state="visible", timeout=5000)
        
        # Scroll into view
        await frame.scroll_into_view_if_needed(selector)
        
        # Hover first for more human-like interaction
        await frame.hover(selector)
        await asyncio.sleep(0.5)
        
        # Click the element
        await frame.click(selector)
        
        logger.debug(f"Clicked element {selector}")
        return True
    except Exception as e:
        logger.error(f"Error clicking element {selector}: {e}")
        return False

async def upload_file(page: Page, selector: str, file_path: str, frame_id: str = None) -> bool:
    """
    Upload a file.
    
    Args:
        page: Playwright page object
        selector: Selector for the file input
        file_path: Path to the file to upload
        frame_id: Optional frame ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the target frame
        frame = page.frame(name=frame_id) if frame_id else page.main_frame
        if not frame:
            logger.error(f"Frame {frame_id} not found")
            return False
            
        # Make sure file exists
        if not os.path.exists(file_path):
            logger.error(f"File {file_path} does not exist")
            return False
            
        # Upload the file
        await frame.set_input_files(selector, file_path)
        
        logger.debug(f"Uploaded file {file_path} to {selector}")
        return True
    except Exception as e:
        logger.error(f"Error uploading file to {selector}: {e}")
        return False

async def check_option(page: Page, selector: str, check: bool = True, frame_id: str = None) -> bool:
    """
    Check or uncheck a checkbox or radio button.
    
    Args:
        page: Playwright page object
        selector: Selector for the element
        check: Whether to check (True) or uncheck (False)
        frame_id: Optional frame ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the target frame
        frame = page.frame(name=frame_id) if frame_id else page.main_frame
        if not frame:
            logger.error(f"Frame {frame_id} not found")
            return False
            
        # Check current state
        is_checked = await frame.is_checked(selector)
        
        # Only take action if needed
        if (check and not is_checked) or (not check and is_checked):
            if check:
                await frame.check(selector)
                logger.debug(f"Checked {selector}")
            else:
                await frame.uncheck(selector)
                logger.debug(f"Unchecked {selector}")
        else:
            logger.debug(f"No action needed for {selector} - already in desired state")
            
        return True
    except Exception as e:
        logger.error(f"Error setting checkbox {selector} to {check}: {e}")
        return False

async def wait_for_navigation(page: Page) -> bool:
    """
    Wait for page navigation to complete.
    
    Args:
        page: Playwright page object
        
    Returns:
        True if successful, False otherwise
    """
    try:
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)  # Small additional delay
        logger.debug("Navigation complete")
        return True
    except Exception as e:
        logger.error(f"Error waiting for navigation: {e}")
        return False 