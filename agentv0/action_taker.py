from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
import logging
import os # Needed for checking file paths
import time # For delays
import random # For randomization

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def scroll_into_view(page, selector):
    """Scroll an element into view before interacting with it.
    
    Args:
        page: The Playwright page object
        selector: The selector to locate the element
        
    Returns:
        True if element was found and scrolled into view, False otherwise
    """
    try:
        element = page.locator(selector).first
        
        # First check if element exists at all
        if element.count() == 0:
            logging.error(f"Element {selector} not found in the DOM")
            return False
            
        # Check initial visibility
        initial_visible = element.is_visible(timeout=1000)
        if not initial_visible:
            logging.info(f"Element {selector} initially not visible, attempting scroll...")
            
            # Try standard scroll into view
            element.scroll_into_view_if_needed(timeout=1000)
            page.wait_for_timeout(500)  # Brief pause after scrolling
            
            # Check visibility after first scroll
            if not element.is_visible(timeout=1000):
                # Try a secondary approach - scroll via JS for more reliable positioning
                try:
                    page.evaluate(f"""
                        (() => {{
                            const el = document.querySelector('{selector}');
                            if (el) {{
                                // Scroll with margin to avoid element being at the very edge
                                el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                                return true;
                            }}
                            return false;
                        }})()
                    """)
                    page.wait_for_timeout(500)  # Wait for scroll to complete
                except Exception as js_err:
                    logging.warning(f"JS scrolling failed for {selector}: {js_err}")
                
                # Final visibility check
                if not element.is_visible(timeout=1000):
                    logging.warning(f"Element {selector} still not visible after multiple scroll attempts")
                    # One last check - some elements are technically "visible" but have 0 dimensions
                    try:
                        box = element.bounding_box()
                        if not box or box['width'] < 2 or box['height'] < 2:
                            logging.warning(f"Element {selector} has negligible dimensions: {box}")
                            return False
                    except Exception:
                        return False
                    return False
        
        # Check if element is in viewport and not obscured
        in_viewport = page.evaluate(f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (!el) return false;
                
                // Check if element is in viewport
                const rect = el.getBoundingClientRect();
                const windowHeight = window.innerHeight || document.documentElement.clientHeight;
                const windowWidth = window.innerWidth || document.documentElement.clientWidth;
                
                const vertInView = (rect.top >= 0 && rect.top <= windowHeight) || 
                                   (rect.bottom >= 0 && rect.bottom <= windowHeight);
                const horInView = (rect.left >= 0 && rect.left <= windowWidth) || 
                                  (rect.right >= 0 && rect.right <= windowWidth);
                
                return vertInView && horInView;
            }})()
        """)
        
        if not in_viewport:
            logging.warning(f"Element {selector} is visible but may not be fully in viewport")
            # Try one more centering scroll
            page.evaluate(f"""
                (() => {{
                    const el = document.querySelector('{selector}');
                    if (el) el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                }})()
            """)
            page.wait_for_timeout(500)
            
        # Add randomized small wait to appear more human-like
        wait_time = random.uniform(100, 300)
        page.wait_for_timeout(wait_time)
        
        logging.info(f"Element {selector} is now scrolled into view and visible")
        return True
    except Exception as e:
        logging.error(f"Error scrolling element {selector} into view: {e}")
        return False

def add_random_delay(min_delay=0.5, max_delay=1.5):
    """Add a random delay between actions to appear more human-like."""
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)
    return delay

def fill_field(page, selector, value):
    """Fill a text field with the given value."""
    try:
        # Ensure element is in view
        if not scroll_into_view(page, selector):
            logging.warning(f"Element {selector} not visible after scroll attempt")
            return False
            
        # Add human-like delay before typing
        add_random_delay()
        
        # Clear field first if it has content
        current_value = page.locator(selector).input_value()
        if current_value:
            page.locator(selector).fill("")
            add_random_delay(0.2, 0.5)
        
        # Type the value (slower, more human-like)
        page.locator(selector).fill(value)
        logging.info(f"Filled field {selector} with value: {value}")
        return True
    except Exception as e:
        logging.error(f"Error filling field {selector}: {e}")
        return False

def select_option(page, selector, value):
    """Select an option from a dropdown."""
    try:
        # Ensure element is in view
        if not scroll_into_view(page, selector):
            logging.warning(f"Element {selector} not visible after scroll attempt")
            return False
            
        add_random_delay()
        
        # Try multiple selection strategies
        try:
            # Try by value first
            page.select_option(selector, value=value)
        except Exception:
            try:
                # Try by label next
                page.select_option(selector, label=value)
            except Exception:
                # Try by text as last resort
                select_el = page.locator(selector)
                options = select_el.locator('option')
                count = options.count()
                
                for i in range(count):
                    option = options.nth(i)
                    if value.lower() in option.inner_text().lower():
                        option.click()
                        break
                else:
                    # If no matching option found, try clicking and typing for custom dropdowns
                    select_el.click()
                    page.keyboard.type(value)
                    page.keyboard.press('Enter')
        
        logging.info(f"Selected option {value} in dropdown {selector}")
        return True
    except Exception as e:
        logging.error(f"Error selecting option in {selector}: {e}")
        return False

def check_checkbox(page, selector):
    """Check a checkbox."""
    try:
        # Ensure element is in view
        if not scroll_into_view(page, selector):
            logging.warning(f"Element {selector} not visible after scroll attempt")
            return False
            
        add_random_delay()
        
        # Only check if not already checked
        if not page.locator(selector).is_checked():
            page.locator(selector).check()
            logging.info(f"Checked checkbox {selector}")
        else:
            logging.info(f"Checkbox {selector} was already checked")
        return True
    except Exception as e:
        logging.error(f"Error checking checkbox {selector}: {e}")
        return False

def uncheck_checkbox(page, selector):
    """Uncheck a checkbox."""
    try:
        # Ensure element is in view
        if not scroll_into_view(page, selector):
            logging.warning(f"Element {selector} not visible after scroll attempt")
            return False
            
        add_random_delay()
        
        # Only uncheck if checked
        if page.locator(selector).is_checked():
            page.locator(selector).uncheck()
            logging.info(f"Unchecked checkbox {selector}")
        else:
            logging.info(f"Checkbox {selector} was already unchecked")
        return True
    except Exception as e:
        logging.error(f"Error unchecking checkbox {selector}: {e}")
        return False

def select_radio(page, selector, value):
    """Select a radio button."""
    try:
        # Ensure element is in view
        if not scroll_into_view(page, selector):
            logging.warning(f"Element {selector} not visible after scroll attempt")
            return False
            
        add_random_delay()
        
        # For radio groups, we might need to select a specific option
        if '[]' in selector or '[type="radio"]' in selector:
            # This is likely a radio group, try to find option matching value
            base_selector = selector.replace('[]', '')
            option_selector = f"{base_selector}[value='{value}']"
            
            try:
                # Try direct value match first
                radio = page.locator(option_selector).first
                radio.check()
                logging.info(f"Selected radio option with value {value}")
                return True
            except Exception:
                # Try finding by label text
                radio_labels = page.locator(f"label:has-text('{value}')")
                count = radio_labels.count()
                
                for i in range(count):
                    label = radio_labels.nth(i)
                    try:
                        # Try clicking the label (which should check the radio)
                        label.click()
                        logging.info(f"Selected radio via label text '{value}'")
                        return True
                    except Exception:
                        continue
                
                logging.warning(f"Could not find radio option with value or label '{value}'")
                return False
        else:
            # Single radio button
            page.locator(selector).check()
            logging.info(f"Selected radio {selector}")
            return True
    except Exception as e:
        logging.error(f"Error selecting radio {selector}: {e}")
        return False

def upload_file(page, selector, file_path):
    """Upload a file."""
    try:
        # Ensure element is in view
        if not scroll_into_view(page, selector):
            logging.warning(f"Element {selector} not visible after scroll attempt")
            return False
            
        add_random_delay()
        
        # Check if file exists
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            return False
            
        # Set the file input
        page.locator(selector).set_input_files(file_path)
        logging.info(f"Uploaded file {file_path} to {selector}")
        
        # Wait for potential upload processing
        page.wait_for_timeout(1000)
        return True
    except Exception as e:
        logging.error(f"Error uploading file to {selector}: {e}")
        return False

def click_button(page, selector):
    """Click a button."""
    try:
        # Ensure element is in view
        if not scroll_into_view(page, selector):
            logging.warning(f"Element {selector} not visible after scroll attempt")
            return False
            
        add_random_delay()
        
        # Click the button and wait for potential navigation
        page.locator(selector).click()
        page.wait_for_timeout(1000)  # Wait a bit for any response
        logging.info(f"Clicked button {selector}")
        return True
    except Exception as e:
        logging.error(f"Error clicking button {selector}: {e}")
        return False

# Example Usage (for testing)
if __name__ == '__main__':
    # This requires a running browser and a page navigated to a test form
    # For simplicity, we assume 'page' object is available. 
    # In real testing, you'd integrate with browser_controller.
    print("ActionTaker module loaded. Run integration tests via main_v0.py or a dedicated test suite.")
    
    # Dummy example calls (won't run without a page)
    # fill_field(None, '#first_name', 'Test')
    # select_option(None, '#country', 'United States')
    # upload_file(None, '#resume', '/path/to/fake_resume.pdf')
    # click_button(None, text='Submit Application')
