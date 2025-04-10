"""Base class for action handlers."""
import logging
from playwright.async_api import Frame
import re

class BaseActionHandler:
    def __init__(self, browser_manager, form_interaction, element_selector):
        self.browser_manager = browser_manager
        self.form_interaction = form_interaction
        self.element_selector = element_selector # Added element_selector
        self.logger = logging.getLogger(self.__class__.__name__)

    async def execute(self, context):
        raise NotImplementedError("Subclasses must implement the execute method.")

    async def _get_frame(self, frame_id: str | None) -> Frame:
        """Helper to get the specified frame or main frame."""
        frame = await self.browser_manager.get_frame(frame_id)
        if not frame:
            error_msg = f"Could not get frame (ID: {frame_id})"
            self.logger.error(error_msg)
            # Consider raising a specific exception here
            raise ValueError(error_msg)
        return frame

    async def _sanitize_selector(self, selector: str) -> str:
        """Sanitize potentially problematic selectors (e.g., numeric IDs)."""
        if not selector:
            return selector
        # First check if it's a numeric ID
        if selector.startswith('#') and selector[1:].isdigit():
            sanitized = f"[id='{selector[1:]}']"
            self.logger.debug(f"Sanitized numeric ID selector '{selector}' to '{sanitized}'")
            return sanitized
        
        # Check if it's an ID with characters that might need escaping
        # CSS.escape might be more robust, but this covers common cases for now.
        if selector.startswith('#') and re.search(r'[:.[\]\s]', selector[1:]):
             id_val = selector[1:].replace("'", "\\'") # Escape single quotes for CSS
             sanitized = f"[id='{id_val}']"
             self.logger.debug(f"Sanitized ID with special chars '{selector}' to '{sanitized}'")
             return sanitized
            
        return selector
    
    async def _ensure_element_visibility(self, frame: Frame, selector: str):
        """Ensures an element is visible before interacting with it."""
        try:
            # Use frame.locator for Playwright's auto-waiting and visibility checks
            locator = frame.locator(selector)
            await locator.wait_for(state='visible', timeout=5000) # Wait up to 5s for visibility
            
            # Optional: Scroll into view if needed, locator handles this often but explicit can help
            try:
                await locator.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                 self.logger.debug(f"Could not scroll {selector} into view, might be okay.")
            
            # Final check (redundant with wait_for, but safe)
            if not await locator.is_visible():
                self.logger.warning(f"Element {selector} still not visible after checks.")
                return False

            return True
        except Exception as e:
            # Ensure the exception object is converted to string for logging
            self.logger.error(f"Error ensuring visibility for {selector}: {str(e)}")
            return False 