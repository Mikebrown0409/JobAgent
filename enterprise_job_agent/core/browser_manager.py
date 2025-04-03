"""Core browser management for the job application system."""

import asyncio
import logging
import os
from typing import Dict, Any, Optional, List
from contextlib import nullcontext
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Frame, Error

from enterprise_job_agent.core.frame_manager import AdvancedFrameManager
from enterprise_job_agent.core.browser_interface import BrowserInterface
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.tools.element_selector import ElementSelector
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager

logger = logging.getLogger(__name__)

class BrowserManager:
    """Manages browser sessions and interactions."""
    
    def __init__(
        self,
        visible: bool = False,
        diagnostics_manager: Optional[DiagnosticsManager] = None
    ):
        """Initialize the browser manager.
        
        Args:
            visible: Whether to show the browser window
            diagnostics_manager: Optional diagnostics manager
        """
        self.visible = visible
        self.diagnostics_manager = diagnostics_manager
        self.logger = logging.getLogger(__name__)
        
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.frame_manager = None
        
        # Initialize tools
        self.element_selector = ElementSelector(self, diagnostics_manager)
        self.form_interaction = FormInteraction(self, self.element_selector, diagnostics_manager)
    
    async def initialize(self) -> bool:
        """Initialize the browser manager.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=not self.visible)
            self.context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 1024},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.93 Safari/537.36'
            )
            self.page = await self.context.new_page()
            
            # Initialize Frame Manager
            self.frame_manager = AdvancedFrameManager(self.page)
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(True)
            self.logger.info("Browser initialized")
            return True
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=str(e)
                )
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
            await self.page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Clear frame cache after navigation
            if self.frame_manager:
                await self.frame_manager.map_all_frames()
                await self.frame_manager.reset_cached_selectors()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            return False
    
    async def goto(self, url: str) -> bool:
        """
        Alias for navigate method to maintain compatibility.
        
        Args:
            url: URL to navigate to
            
        Returns:
            True if navigation successful, False otherwise
        """
        return await self.navigate(url)
    
    async def get_frame(self, frame_identifier: Optional[str] = None) -> Frame:
        """
        Get a frame using the AdvancedFrameManager.
        
        Args:
            frame_identifier: Frame identifier (e.g., 'main', name, ID, or derived identifier)
            
        Returns:
            Frame object or main page frame if identifier is None, 'main', or not found.
        """
        if not frame_identifier or frame_identifier == "main":
            return self.page.main_frame
        
        if not self.frame_manager:
            logger.error("AdvancedFrameManager is not initialized.")
            return self.page.main_frame
        
        target_frame = self.frame_manager.frames.get(frame_identifier)
        
        if target_frame:
            try:
                await target_frame.url()
                return target_frame
            except Error:
                logger.warning(f"Frame '{frame_identifier}' found but seems detached.")
                return self.page.main_frame
        else:
            logger.warning(f"Frame identifier '{frame_identifier}' not found.")
            return self.page.main_frame
    
    async def take_screenshot(self, path: str) -> bool:
        """Take a screenshot of the current page.
        
        Args:
            path: Path to save the screenshot to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.page.screenshot(path=path)
            return True
        except Exception as e:
            self.logger.error(f"Error taking screenshot: {str(e)}")
            return False

    async def get_page_html(self) -> str:
        """Get the HTML content of the current page.
        
        Returns:
            HTML content of the page
        """
        try:
            # Get the full HTML content of the page
            html_content = await self.page.content()
            return html_content
        except Exception as e:
            self.logger.error(f"Error getting page HTML: {str(e)}")
            return ""
            
    async def scroll_to_element(self, selector: str, frame_id: Optional[str] = None) -> bool:
        """Scroll to make an element visible.
        
        Args:
            selector: CSS selector for the element
            frame_id: Optional frame ID if element is in a frame
            
        Returns:
            True if scrolling succeeded, False otherwise
        """
        try:
            # Sanitize the selector if it's numeric
            safe_selector = self._sanitize_selector(selector)
            
            if frame_id:
                frame = await self.frame_manager.get_frame_by_id(frame_id)
                if not frame:
                    self.logger.error(f"Frame {frame_id} not found")
                    return False
                await frame.scroll_into_view_if_needed(safe_selector)
            else:
                await self.page.query_selector(safe_selector)
                await self.page.evaluate(f"""(selector) => {{
                    const element = document.querySelector(selector);
                    if (element) {{
                        element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        return true;
                    }}
                    return false;
                }}""", safe_selector)
            return True
        except Exception as e:
            self.logger.error(f"Error scrolling to element {selector}: {str(e)}")
            return False
            
    def _sanitize_selector(self, selector: str) -> str:
        """Sanitize a selector to ensure it's valid for CSS and JS operations.
        
        Args:
            selector: The original selector string
            
        Returns:
            A sanitized selector that will work with DOM operations
        """
        # If selector starts with # (ID selector)
        if selector.startswith('#'):
            selector_id = selector[1:]  # Remove the # prefix
            
            # For numeric IDs or IDs with numeric prefixes
            if selector_id.isdigit() or selector_id[0].isdigit():
                # Use attribute selector instead of ID selector for numeric IDs
                return f"[id='{selector_id}']"
                
        return selector
    
    async def get_element_info(self, selector: str, frame_identifier: Optional[str] = None) -> Dict[str, Any]:
        """Get detailed information about an element.
        
        Args:
            selector: CSS selector for the element
            frame_identifier: Optional frame identifier
            
        Returns:
            Dictionary with element information
        """
        try:
            frame = await self.get_frame(frame_identifier)
            element = await frame.query_selector(selector)
            
            if not element:
                self.logger.warning(f"Element {selector} not found")
                return {}
                
            # Get element properties
            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
            
            # Get attributes
            attrs = await element.evaluate("""el => {
                const result = {};
                for (const attr of el.attributes) {
                    result[attr.name] = attr.value;
                }
                return result;
            }""")
            
            # Get classes as a list
            classes = await element.evaluate("el => Array.from(el.classList)")
            
            return {
                "tag_name": tag_name,
                "attributes": attrs,
                "classes": classes,
                "selector": selector
            }
            
        except Exception as e:
            self.logger.error(f"Error getting element info for {selector}: {str(e)}")
            return {}
            
    async def wait_for_load(self, timeout: int = 30000) -> bool:
        """Wait for the page to load fully.
        
        Args:
            timeout: Timeout in milliseconds
            
        Returns:
            True if the page loaded successfully, False otherwise
        """
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
            return True
        except Exception as e:
            self.logger.error(f"Error waiting for page to load: {str(e)}")
            return False
            
    async def close(self) -> None:
        """Close the browser manager."""
        with self.diagnostics_manager.track_stage("browser_close") if self.diagnostics_manager else nullcontext():
            try:
                if self.page:
                    await self.page.close()
                if self.context:
                    await self.context.close()
                if self.browser:
                    await self.browser.close()
                if self.playwright:
                    await self.playwright.stop()
                    
                # Reset variables
                self.page = None
                self.context = None
                self.browser = None
                self.playwright = None
            except Exception as e:
                self.logger.error(f"Error closing browser: {str(e)}")
                if self.diagnostics_manager:
                    self.diagnostics_manager.end_stage(False)

    def get_page(self):
        """Get the current page object.
        
        Returns:
            The current page object
        """
        return self.page 