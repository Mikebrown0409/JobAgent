"""Browser management for the enterprise job application system."""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Frame, Locator, Error

logger = logging.getLogger(__name__)

class BrowserManager:
    """Manages browser interactions for job applications."""
    
    def __init__(self, headless: bool = True):
        """
        Initialize the browser manager.
        
        Args:
            headless: Whether to run in headless mode
        """
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.frame_cache = {}
        
    async def start(self) -> bool:
        """
        Start the browser.
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            logger.info(f"Starting browser in {'headless' if self.headless else 'visible'} mode")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=self.headless)
            self.context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 900},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'
            )
            self.page = await self.context.new_page()
            logger.info("Browser started successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            return False
    
    async def navigate(self, url: str) -> bool:
        """
        Navigate to a URL.
        
        Args:
            url: URL to navigate to
            
        Returns:
            True if navigation successful, False otherwise
        """
        try:
            logger.info(f"Navigating to {url}")
            await self.page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Clear frame cache after navigation
            self.frame_cache = {}
            
            logger.info(f"Successfully navigated to {url}")
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            return False
    
    async def get_page(self) -> Page:
        """
        Get the current page.
        
        Returns:
            Current page
        """
        return self.page
    
    async def take_screenshot(self, path: str) -> str:
        """
        Take a screenshot.
        
        Args:
            path: Path to save screenshot
            
        Returns:
            Path to saved screenshot
        """
        try:
            logger.info(f"Taking screenshot: {path}")
            await self.page.screenshot(path=path, full_page=True)
            logger.info(f"Screenshot saved to {path}")
            return path
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            return ""
    
    async def get_frame(self, frame_identifier: Optional[str] = None) -> Frame:
        """
        Get a frame by identifier.
        
        Args:
            frame_identifier: Frame identifier (URL, name, or ID)
            
        Returns:
            Frame object or main page if no identifier provided
        """
        if not frame_identifier or frame_identifier == "main":
            return self.page.main_frame
        
        # Check cache first
        if frame_identifier in self.frame_cache:
            frame = self.frame_cache[frame_identifier]
            try:
                # Verify the frame is still valid by checking its URL
                await frame.url()
                return frame
            except Exception:
                # Frame is no longer valid, remove from cache
                del self.frame_cache[frame_identifier]
        
        # Look for frame by URL, name, or ID
        try:
            frames = self.page.frames
            for frame in frames:
                frame_url = frame.url
                frame_name = await frame.name() if hasattr(frame, "name") else ""
                
                # Check if the frame matches any of the identifiers
                if (
                    frame_identifier in frame_url or 
                    frame_identifier == frame_name or
                    await self._frame_has_id(frame, frame_identifier)
                ):
                    # Cache the frame for future use
                    self.frame_cache[frame_identifier] = frame
                    return frame
            
            # If no match found, try to find iframe by selector and get its frame
            iframe_locator = self.page.locator(f"iframe[src*='{frame_identifier}'], iframe[id='{frame_identifier}'], iframe[name='{frame_identifier}']")
            if await iframe_locator.count() > 0:
                iframe = iframe_locator.first
                frame_handle = await iframe.content_frame()
                if frame_handle:
                    # Cache the frame for future use
                    self.frame_cache[frame_identifier] = frame_handle
                    return frame_handle
        except Exception as e:
            logger.error(f"Error finding frame {frame_identifier}: {e}")
        
        # If all else fails, return main frame
        logger.warning(f"Frame {frame_identifier} not found, falling back to main frame")
        return self.page.main_frame
    
    async def _frame_has_id(self, frame: Frame, frame_id: str) -> bool:
        """
        Check if a frame has the specified ID.
        
        Args:
            frame: Frame to check
            frame_id: ID to check for
            
        Returns:
            True if frame has the ID, False otherwise
        """
        try:
            iframe_element = await self.page.query_selector(f"iframe[id='{frame_id}']")
            if iframe_element:
                frame_handle = await iframe_element.content_frame()
                return frame_handle == frame
        except Exception:
            pass
        return False
    
    async def extract_job_details(self) -> Dict[str, Any]:
        """
        Extract job details from the page.
        
        Returns:
            Dictionary with job details
        """
        try:
            # Extract job title
            title_elem = self.page.locator("h1").first
            title = await title_elem.text_content() if await title_elem.count() > 0 else "Unknown Position"
            
            # Extract job description
            desc_elem = self.page.locator(".description").first
            description = await desc_elem.text_content() if await desc_elem.count() > 0 else ""
            
            # If description not found, try alternative selectors
            if not description:
                desc_selectors = [
                    ".job-description",
                    "#job-description",
                    "[data-test='job-description']",
                    ".posting-requirements",
                    ".job-post-description"
                ]
                
                for selector in desc_selectors:
                    desc_elem = self.page.locator(selector).first
                    if await desc_elem.count() > 0:
                        description = await desc_elem.text_content()
                        if description:
                            break
            
            # Extract company name
            company_elem = self.page.locator(".company-name, .company, .organization-name").first
            company = await company_elem.text_content() if await company_elem.count() > 0 else "Unknown Company"
            
            # Return job details
            return {
                "title": title.strip(),
                "company": company.strip(),
                "description": description.strip()
            }
        except Exception as e:
            logger.error(f"Error extracting job details: {e}")
            return {
                "title": "Unknown Position",
                "company": "Unknown Company",
                "description": "Failed to extract job description"
            }
    
    async def fill_field(self, selector: str, value: str, frame_identifier: Optional[str] = None) -> bool:
        """
        Fill a field with a value.
        
        Args:
            selector: Field selector
            value: Value to fill
            frame_identifier: Optional frame identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            frame = await self.get_frame(frame_identifier)
            field = frame.locator(selector)
            
            if await field.count() == 0:
                logger.warning(f"Field {selector} not found in frame {frame_identifier}")
                return False
            
            # Check if the field is a select element
            is_select = await frame.evaluate(f"() => document.querySelector('{selector}')?.tagName?.toLowerCase() === 'select'")
            
            if is_select:
                # Handle select dropdown
                await field.select_option(value)
            else:
                # Clear the field first
                await field.fill("")
                # Fill the field
                await field.fill(value)
            
            logger.info(f"Filled field {selector} with value: {value}")
            return True
        except Exception as e:
            logger.error(f"Error filling field {selector}: {e}")
            return False
    
    async def select_custom_dropdown(\
        self, \
        trigger_selector: str, \
        options_selector: str, \
        value_to_select: str, \
        frame_identifier: Optional[str] = None\
    ) -> bool:
        """
        Select an option from a custom dropdown (not a standard <select>).

        Args:
            trigger_selector: Selector for the element that opens the dropdown.
            options_selector: Selector for the individual option elements within the dropdown.
            value_to_select: The exact text content of the option to select.
            frame_identifier: Optional frame identifier.

        Returns:
            True if successful, False otherwise.
        """
        try:
            frame = await self.get_frame(frame_identifier)
            trigger_element = frame.locator(trigger_selector)

            if await trigger_element.count() == 0:
                logger.warning(f"Dropdown trigger {trigger_selector} not found in frame {frame_identifier}")
                return False

            logger.debug(f"Clicking dropdown trigger: {trigger_selector}")
            await trigger_element.click()

            # Wait briefly for options to potentially appear/animate
            await frame.wait_for_timeout(500) 

            # Wait for at least one option to be visible
            try:
                await frame.locator(options_selector).first.wait_for(state="visible", timeout=10000)
            except Error as e:
                logger.warning(f"Dropdown options ({options_selector}) did not become visible after clicking trigger {trigger_selector}: {e}")
                # Attempt to dismiss and return failure
                try:
                    await frame.locator("body").click(timeout=1000) 
                except Error: pass # Ignore error if body click fails
                return False

            options = frame.locator(options_selector)
            option_count = await options.count()
            logger.debug(f"Found {option_count} options matching: {options_selector}")

            selected = False
            for i in range(option_count):
                option = options.nth(i)
                try:
                    option_text = (await option.text_content() or "").strip()
                    if option_text == value_to_select:
                        logger.info(f"Found matching option '{option_text}'. Clicking.")
                        await option.click()
                        selected = True
                        break
                except Error as e:
                    logger.warning(f"Error processing option {i} for selector {options_selector}: {e}")
                    continue # Try next option

            if not selected:
                logger.warning(f"Could not find option with text '{value_to_select}' in dropdown triggered by {trigger_selector}")

            # Attempt to dismiss the dropdown by clicking the body, regardless of selection success
            try:
                logger.debug("Attempting to dismiss dropdown by clicking body")
                await frame.locator("body").click(timeout=1000) # Short timeout for dismissal
            except Error as e:
                logger.warning(f"Could not click body to dismiss dropdown: {e}")
                # Don't necessarily fail the whole operation if dismissal click fails

            return selected

        except Error as e:
            logger.error(f"Error interacting with custom dropdown {trigger_selector}: {e}")
            # Attempt to dismiss if an error occurred mid-operation
            try:
                frame = await self.get_frame(frame_identifier)
                await frame.locator("body").click(timeout=1000)
            except Error: pass 
            return False
    
    async def fill_date_field(self, selector: str, date_value: str, frame_identifier: Optional[str] = None) -> bool:
        """
        Fill a date input field with a date string.
        
        Assumes the date field accepts direct text input in a common format (e.g., YYYY-MM-DD, MM/DD/YYYY).
        
        Args:
            selector: Date field selector.
            date_value: The date string to fill.
            frame_identifier: Optional frame identifier.
            
        Returns:
            True if successful, False otherwise.
        """
        logger.info(f"Attempting to fill date field {selector} with value '{date_value}'")
        # Directly use fill_field, assuming the input accepts text.
        # More complex calendar interaction can be added if needed.
        return await self.fill_field(selector, date_value, frame_identifier)
    
    async def upload_file(self, selector: str, file_path: str, frame_identifier: Optional[str] = None) -> bool:
        """
        Upload a file to a file input element.

        Args:
            selector: Selector for the <input type="file"> element.
            file_path: The absolute or relative path to the file to upload.
            frame_identifier: Optional frame identifier.

        Returns:
            True if successful, False otherwise.
        """
        try:
            frame = await self.get_frame(frame_identifier)
            file_input = frame.locator(selector)

            if await file_input.count() == 0:
                logger.warning(f"File input {selector} not found in frame {frame_identifier}")
                return False

            # Verify the element is an input type=file
            is_file_input = await file_input.evaluate("el => el.tagName === 'INPUT' && el.type === 'file'")
            if not is_file_input:
                logger.warning(f"Element {selector} is not an <input type=\"file\">")
                return False

            logger.info(f"Uploading file '{file_path}' to input {selector}")
            await file_input.set_input_files(file_path)
            logger.info(f"Successfully set input file for {selector}")
            return True
            
        except FileNotFoundError:
            logger.error(f"File not found for upload: {file_path}")
            return False
        except Error as e:
            logger.error(f"Error uploading file to {selector}: {e}")
            return False
    
    async def set_checkbox_radio(self, selector: str, should_be_checked: bool = True, frame_identifier: Optional[str] = None) -> bool:
        """
        Set the state of a checkbox or radio button.

        Args:
            selector: Selector for the <input type=\"checkbox\"> or <input type=\"radio\">.
            should_be_checked: Whether the element should end up checked (True) or unchecked (False).
                               For radio buttons, this is typically always True.
            frame_identifier: Optional frame identifier.

        Returns:
            True if successful, False otherwise.
        """
        try:
            frame = await self.get_frame(frame_identifier)
            element = frame.locator(selector)

            if await element.count() == 0:
                logger.warning(f"Checkbox/radio {selector} not found in frame {frame_identifier}")
                return False

            element_type = await element.evaluate("el => el.type")
            if element_type not in ["checkbox", "radio"]:
                 logger.warning(f"Element {selector} is not a checkbox or radio button (type: {element_type})")
                 # Still might be a clickable label/span, attempt click if checking
                 if should_be_checked:
                     logger.debug(f"Attempting direct click on {selector} as it might be a label/custom element")
                     await element.click()
                     # Cannot easily verify success here without knowing the underlying input state
                     return True 
                 else:
                     return False # Cannot reliably uncheck a non-input element this way
            
            current_state = await element.is_checked()
            logger.debug(f"Checkbox/radio {selector} current state: {current_state}, desired state: {should_be_checked}")

            if current_state != should_be_checked:
                logger.info(f"Clicking {selector} to change state to {should_be_checked}")
                await element.click() # click() often more robust than check()/uncheck()
                
                # Verify state after click
                await asyncio.sleep(0.1) # Brief pause for state update
                new_state = await element.is_checked()
                if new_state != should_be_checked:
                    logger.warning(f"State change failed for {selector}. Expected {should_be_checked}, got {new_state}")
                    return False
            else:
                logger.info(f"Checkbox/radio {selector} is already in the desired state ({should_be_checked})")

            return True

        except Error as e:
            logger.error(f"Error setting checkbox/radio {selector}: {e}")
            return False
    
    async def click_element(self, selector: str, frame_identifier: Optional[str] = None) -> bool:
        """
        Click an element.
        
        Args:
            selector: Element selector
            frame_identifier: Optional frame identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            frame = await self.get_frame(frame_identifier)
            element = frame.locator(selector)
            
            if await element.count() == 0:
                logger.warning(f"Element {selector} not found in frame {frame_identifier}")
                return False
            
            await element.click()
            logger.info(f"Clicked element {selector}")
            return True
        except Exception as e:
            logger.error(f"Error clicking element {selector}: {e}")
            return False
    
    async def dismiss_dropdown(self) -> bool:
        """
        Dismiss any active dropdown by clicking elsewhere.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Click in an empty area of the page to dismiss dropdown
            await self.page.mouse.click(10, 10)
            return True
        except Exception as e:
            logger.error(f"Error dismissing dropdown: {e}")
            return False
    
    async def close(self) -> None:
        """Close the browser."""
        try:
            if self.browser:
                logger.info("Closing browser")
                await self.browser.close()
                self.browser = None
            
            if self.playwright:
                logger.info("Closing playwright")
                await self.playwright.stop()
                self.playwright = None
        except Exception as e:
            logger.error(f"Error closing browser: {e}") 