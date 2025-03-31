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