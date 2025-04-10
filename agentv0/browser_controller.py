from playwright.sync_api import sync_playwright, Page, Browser, Playwright
import logging
from playwright_stealth import stealth_sync # Import stealth
import re # For label cleaning
from typing import Optional
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Common User Agent String (Example: Chrome on Mac)
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

def launch_browser(headless: bool = True) -> tuple[Playwright, Browser, Page]:
    """Launches Playwright, creates a browser instance, applies stealth, and returns a new page."""
    logging.info("Launching browser with stealth...")
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=headless)
        # Create context with user agent and viewport
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={'width': 1920, 'height': 1080} # Common desktop resolution
        )
        page = context.new_page()
        
        # Apply stealth patches
        stealth_sync(page)
        
        logging.info("Browser launched successfully with stealth measures.")
        # Return context as well, might be needed for cleanup? Check playwright docs.
        # For now, returning p, browser, page is consistent with previous version.
        return p, browser, page 
    except Exception as e:
        logging.error(f"Failed to launch browser: {e}")
        raise

def navigate_to(page: Page, url: str) -> tuple[bool, Optional[str]]:
    """Navigates the page to the specified URL. Returns (success_bool, error_msg_or_none)."""
    logging.info(f"Navigating to {url}...")
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=60000) # 60 second timeout
        logging.info(f"Successfully navigated to {url}.")
        return True, None # Indicate success
    except Exception as e:
        logging.error(f"Failed to navigate to {url}: {e}")
        return False, str(e) # Indicate failure and return error message

def find_form_fields_robust(page: Page) -> list[dict]:
    """Finds form fields using a more robust, visually/structurally oriented approach."""
    logging.info("Scanning for form fields (robust method)...")
    fields = []
    processed_elements = set() # Keep track of elements already processed

    # Broader initial selection of potentially relevant elements
    # Includes inputs, selects, textareas, and elements often used for custom controls
    potential_selectors = [
        'input:not([type="hidden"]):not([type="submit"]):not([type="reset"])',
        'select',
        'textarea',
        '[role="textbox"]', 
        '[role="combobox"]', 
        '[role="listbox"]', 
        '[role="searchbox"]', 
        '[contenteditable="true"]',
        'button[aria-haspopup="listbox"]' # Buttons that open dropdowns
    ]
    combined_selector = ", ".join(potential_selectors)

    try:
        elements = page.locator(combined_selector).all()
        logging.info(f"Found {len(elements)} potential field elements.")

        for element in elements:
            try:
                # --- Visibility and Basic Checks ---
                if not element.is_visible() or not element.is_enabled():
                    continue
                    
                # Check bounding box - skip tiny/invisible elements
                bounding_box = element.bounding_box()
                if not bounding_box or bounding_box['width'] < 5 or bounding_box['height'] < 5:
                     logging.debug(f"Skipping element with negligible bounding box: {bounding_box}")
                     continue
                
                # Deduplication check (using element handle string representation)
                element_handle_str = str(element)
                if element_handle_str in processed_elements:
                    continue
                processed_elements.add(element_handle_str)
                
                # --- Extract Field Details ---
                field_details = {}
                tag_name = element.evaluate('el => el.tagName.toLowerCase()')
                role = element.get_attribute('role')
                field_details['tag_name'] = tag_name
                field_details['role'] = role
                field_details['type'] = element.get_attribute('type') or role or tag_name # Best guess type
                field_details['id'] = element.get_attribute('id')
                field_details['name'] = element.get_attribute('name')
                field_details['data-qa'] = element.get_attribute('data-qa')

                # --- Generate Best Selector --- (Prioritize ID > QA > Name > Relative)
                if field_details['id']:
                    field_details['selector'] = f"#{field_details['id']}"
                elif field_details['data-qa']:
                     field_details['selector'] = f"[data-qa=\"{field_details['data-qa']}\"]"
                elif field_details['name']:
                     escaped_name = field_details['name'].replace(':', '\\:').replace('[', '\\[').replace(']', '\\]')
                     field_details['selector'] = f"{tag_name}[name=\"{escaped_name}\"]"
                else:
                    # Fallback: Try to create a more unique selector based on visible text or role if possible
                    # This part needs significant improvement for real robustness
                    # For now, keep a basic fallback
                    field_details['selector'] = f"{combined_selector} >> internal:control=enter-frame >> visible=true >> nth={len(fields)}" # Less ideal
                    logging.warning(f"No stable ID/QA/Name for {tag_name}, using less stable fallback: {field_details['selector']}")

                # --- Find Label (More Robust Methods) ---
                label_text = ""
                try:
                    # 1. `aria-labelledby` (preferred)
                    aria_labelledby = element.get_attribute('aria-labelledby')
                    if aria_labelledby:
                        label_elements = page.locator(f"#{aria_labelledby}")
                        label_text = " ".join(label_elements.all_text_contents()).strip()
                    
                    # 2. `aria-label`
                    if not label_text: label_text = element.get_attribute('aria-label') or ""
                    
                    # 3. Standard `label[for]`
                    if not label_text and field_details['id']:
                        label = page.locator(f'label[for="{field_details["id"]}"]').first
                        if label.is_visible(timeout=100): label_text = label.text_content().strip()
                        
                    # 4. Closest preceding/ancestor label/strong/h tag (heuristic)
                    if not label_text:
                        # Try finding label within potential wrapper first
                        wrapper = element.locator('xpath=ancestor::div[contains(@class, "field") or contains(@class, "question") or contains(@class, "form-group")][1]').first
                        if wrapper.count() > 0:
                            label_in_wrapper = wrapper.locator('label, strong, h1, h2, h3, h4, h5, h6').first
                            if label_in_wrapper.is_visible(timeout=100): label_text = label_in_wrapper.text_content().strip()
                        
                        # If not in wrapper, check preceding siblings
                        if not label_text:
                             label_element = element.locator('xpath=preceding-sibling::*[self::label or self::div or self::span or self::strong][1]').first
                             if label_element.is_visible(timeout=100):
                                 label_text = label_element.text_content().strip()
                                 
                    # 5. Placeholder text
                    if not label_text: label_text = element.get_attribute('placeholder') or ""

                    # Clean label text (remove required markers etc.)
                    label_text = re.sub(r'\*|\(optional\)', '', label_text, flags=re.IGNORECASE).strip()
                    
                except Exception as e:
                    logging.warning(f"Could not reliably determine label for selector {field_details.get('selector', 'N/A')}: {e}")
                
                field_details['label'] = label_text or "No label found"

                logging.debug(f"Robust detect: Found field {field_details}")
                fields.append(field_details)

            except Exception as inner_e:
                logging.warning(f"Error processing potential element: {inner_e}")
                continue # Skip this element if processing fails

    except Exception as e:
        logging.error(f"Error finding form fields robustly: {e}")

    logging.info(f"Robust field finder identified {len(fields)} fields.")
    return fields

def scrape_job_details(page: Page) -> dict:
    """Attempts to scrape job title and company name from the page.
    Uses common selectors and prioritizes the first match found.
    Returns a dictionary with 'job_title' and 'company_name'.
    """
    details = {"job_title": None, "company_name": None}
    
    # Common selectors for Job Title
    title_selectors = [
        'h1', # Often the main title
        'h2', # Sometimes used
        '[class*="title"]', '[id*="title"]', # Class/ID containing "title"
        '[data-testid*="job-title"]' # Common test IDs
        # TODO: Add more platform-specific selectors if needed
    ]
    
    # Common selectors for Company Name (often near title or logo)
    company_selectors = [
        '[class*="company"]', '[id*="company"]', 
        '[class*="organization"]', '[id*="organization"]',
        'a[href*="/company/"]', # Links to company page
        'div:has(> img[alt*="logo"]) > span', # Span next to logo image
        'div[class*="header"] > *:nth-child(1)', # First element in header-like div
        'p[class*="posting-headline"] > span:nth-child(1)', # Lever specific?
        '[data-qa="company-name"]', # Greenhouse specific QA tag
        '.posting-company', # Another Lever pattern
        '.job-company-name', # Generic class
        '.app-title', # Sometimes company is in app title area
        'meta[property="og:site_name"]', # OpenGraph meta tag (attribute read needed)
        'img[alt*="logo"]' # Alt text of logo (fallback)
    ]

    logging.info("Attempting to scrape job title and company name...")

    # Scrape Job Title
    for selector in title_selectors:
        try:
            element = page.locator(selector).first
            if element.count() > 0 and element.is_visible(timeout=500): # Short timeout
                title_text = element.text_content().strip()
                # Basic filtering (avoid overly long text, might need more refinement)
                if title_text and len(title_text) < 100:
                    logging.info(f"Scraped Job Title '{title_text}' using selector '{selector}'")
                    details["job_title"] = title_text
                    break # Found one, stop looking
        except Exception as e:
            logging.debug(f"Error checking title selector {selector}: {e}")
           
    # Scrape Company Name
    for selector in company_selectors:
        try:
            element = page.locator(selector).first
            if element.count() > 0 and element.is_visible(timeout=500):
                company_text = element.text_content().strip()
                
                # Handle meta tag selector - get content attribute
                if selector.startswith('meta'):
                    company_text = element.get_attribute('content') or ""
                    company_text = company_text.strip()

                # If it's an image logo, try getting text from a nearby element (heuristic)
                if not company_text and selector.startswith('img'):
                    try:
                        # Try parent's text or sibling - this is very basic
                        parent_text = element.locator('xpath=..').text_content().strip()
                        if parent_text and len(parent_text) < 50:
                            company_text = parent_text
                        else: # Try grandparent maybe?
                             parent_text = element.locator('xpath=../..').text_content().strip()
                             if parent_text and len(parent_text) < 50:
                                 company_text = parent_text
                    except Exception:
                        pass # Ignore errors in heuristic lookup

                # Basic filtering
                if company_text and len(company_text) < 100 and "apply" not in company_text.lower():
                    logging.info(f"Scraped Company Name '{company_text}' using selector '{selector}'")
                    details["company_name"] = company_text
                    break
        except Exception as e:
            logging.debug(f"Error checking company selector {selector}: {e}")

    if not details["job_title"]:
        logging.warning("Could not scrape Job Title.")
    if not details["company_name"]:
        logging.warning("Could not scrape Company Name.")
    
    return details

def find_basic_fields(page: Page) -> list:
    # ... (existing find_basic_fields function) ...
    pass

def close_browser(p: Playwright, browser: Browser):
    """Closes the browser and stops Playwright."""
    logging.info("Closing browser...")
    try:
        browser.close()
        p.stop()
        logging.info("Browser closed successfully.")
    except Exception as e:
        logging.error(f"Failed to close browser properly: {e}")

async def check_submission_success(page: Page, timeout: int = 10000) -> bool:
    """
    Checks if the job application submission was likely successful by looking for
    common confirmation messages, elements, or URL patterns.

    Args:
        page: The Playwright Page object after the submit action.
        timeout: Maximum time in milliseconds to wait for indicators.

    Returns:
        True if a success indicator is found, False otherwise.
    """
    logging.info("Checking for application submission success indicators...")
    
    success_keywords = [
        "thank you", "thanks", "application submitted", "submission successful", 
        "received your application", "application complete", "we'll be in touch",
        "you've applied"
    ]
    success_selectors = [
        '[class*="success"]', '[id*="success"]', 
        '[class*="thank"]', '[id*="thank"]', 
        '[class*="confirmation"]', '[id*="confirmation"]'
        # Add more specific selectors if known for certain platforms
    ]
    success_url_patterns = [
        r'/confirmation', r'/success', r'/thank-you', r'/complete', r'/submitted'
        # Add more specific URL patterns if known
    ]

    start_time = time.time()
    while time.time() - start_time < timeout / 1000.0:
        try:
            # 1. Check URL
            current_url = page.url
            for pattern in success_url_patterns:
                if re.search(pattern, current_url, re.IGNORECASE):
                    logging.info(f"Success indicator found: URL matches pattern '{pattern}'.")
                    return True

            # 2. Check visible text content for keywords
            # Using JavaScript to get all visible text might be more robust
            all_text = await page.evaluate("() => document.body.innerText")
            if all_text:
                for keyword in success_keywords:
                    if keyword in all_text.lower():
                        logging.info(f"Success indicator found: Text contains keyword '{keyword}'.")
                        return True

            # 3. Check for success selectors
            for selector in success_selectors:
                elements = page.locator(selector)
                count = await elements.count()
                if count > 0:
                    # Check if at least one is visible
                    for i in range(count):
                         if await elements.nth(i).is_visible(timeout=500): # Short timeout for visibility check
                            logging.info(f"Success indicator found: Visible element matches selector '{selector}'.")
                            return True

            # Brief pause before retrying
            await page.wait_for_timeout(500) 

        except Exception as e:
            logging.warning(f"Error during submission check: {e}. Continuing check...")
            await page.wait_for_timeout(500) # Wait a bit longer if an error occurs

    logging.warning("No definitive success indicators found within the timeout.")
    return False

# Example usage (for testing this module directly)
if __name__ == '__main__':
    playwright_instance, browser_instance, page_instance = None, None, None
    try:
        # Test with a known Greenhouse page (replace with a real one for actual testing)
        test_url = "https://boards.greenhouse.io/embed/job_app?for=lever" # Example Lever page on Greenhouse
        
        playwright_instance, browser_instance, page_instance = launch_browser(headless=False) # Run non-headless for visual check
        navigate_to(page_instance, test_url)
        
        # Give page time to load JS if necessary
        page_instance.wait_for_timeout(3000) 
        
        detected_fields = find_form_fields_robust(page_instance)
        print("\nDetected Fields:")
        for field in detected_fields:
            print(field)
            
    except Exception as e:
        print(f"An error occurred during testing: {e}")
    finally:
        if playwright_instance and browser_instance:
            input("Press Enter to close browser...") # Pause before closing
            close_browser(playwright_instance, browser_instance)
