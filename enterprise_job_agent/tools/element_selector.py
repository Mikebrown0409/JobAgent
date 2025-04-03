"""Tools for selecting and identifying elements in job application forms."""

import logging
from typing import Dict, Any, Optional, List, Tuple
from playwright.async_api import Frame, ElementHandle, Error

from enterprise_job_agent.core.browser_interface import BrowserInterface
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager

logger = logging.getLogger(__name__)

class ElementSelector:
    """Enhanced element selection with smart waiting and retries."""
    
    def __init__(
        self,
        browser: BrowserInterface,
        diagnostics_manager: Optional[DiagnosticsManager] = None
    ):
        """Initialize element selector.
        
        Args:
            browser: Browser interface instance
            diagnostics_manager: Optional diagnostics manager
        """
        self.browser = browser
        self.diagnostics_manager = diagnostics_manager
        self.logger = logger
        self.selector_cache: Dict[str, str] = {}
    
    async def _normalize_selector(self, selector: str) -> str:
        """
        Normalize CSS selector for consistent usage.
        Handles ID normalization and potential selector syntax issues.
        
        Args:
            selector: Original CSS selector
            
        Returns:
            Normalized CSS selector
        """
        # Check if this is an ID selector that starts with '#'
        if selector.startswith('#'):
            selector_id = selector[1:]  # Remove the '#'
            
            # Check if the ID starts with a digit, which is invalid in CSS without escaping
            if selector_id and selector_id[0].isdigit():
                # CSS escape for IDs that start with a digit
                # Format: #\3XXXXX where XXXXX is the codepoint in hex
                codepoint = ord(selector_id[0])
                escaped_id = f"\\3{codepoint:x} {selector_id[1:]}"
                selector = f"#{escaped_id}"
            
            # Handle special characters that need escaping in CSS selectors
            for char in [':', '.', '[', ']', '(', ')', '+', '~', '>', '|', '*']:
                if char in selector_id:
                    # Apply proper escaping by replacing special character with \char
                    selector_id = selector_id.replace(char, f"\\{char}")
                    selector = f"#{selector_id}"
        
        return selector

    async def wait_for_element(
        self,
        selector: str,
        frame: Optional[Any] = None,
        timeout: int = 5000,
        visible: bool = True
    ) -> Any:
        """Wait for an element to be ready for interaction.
        
        Args:
            selector: CSS selector for the element
            frame: Frame to search in (optional)
            timeout: Timeout in milliseconds
            visible: Whether the element should be visible
            
        Returns:
            Element handle if found, None otherwise
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage(f"wait_for_element_{selector}")
            
        try:
            # Normalize selector for CSS compatibility
            normalized_selector = await self._normalize_selector(selector)
            
            # Determine context (frame or page)
            context = frame if frame else self.browser.page
            
            # Wait for element
            element = await context.wait_for_selector(
                normalized_selector,
                state="visible" if visible else "attached",
                timeout=timeout
            )
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(True)
                
            return element
            
        except Exception as e:
            self.logger.debug(f"Element not found: {selector} - {str(e)}")
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=str(e))
                
            return None
    
    async def find_element(
        self,
        selector: str,
        frame: Optional[Frame] = None
    ) -> Optional[ElementHandle]:
        """Find an element without waiting.
        
        Args:
            selector: CSS selector
            frame: Optional frame to search in
            
        Returns:
            ElementHandle if found, None otherwise
        """
        try:
            context = frame or self.browser.page
            return await context.query_selector(selector)
        except Exception as e:
            self.logger.debug(f"Element not found: {selector} - {str(e)}")
            return None
    
    async def find_elements(
        self,
        selector: str,
        frame: Optional[Frame] = None
    ) -> list[ElementHandle]:
        """Find all elements matching a selector.
        
        Args:
            selector: CSS selector for the elements
            frame: Optional frame to search in
            
        Returns:
            List of element handles
        """
        try:
            # Use provided frame or default to page
            context = frame or self.browser.page
            if not context:
                logger.error("No valid context (frame or page) available")
                return []
            
            # Find all matching elements
            elements = await context.query_selector_all(selector)
            return elements
            
        except Exception as e:
            logger.warning(f"Error finding elements {selector}: {e}")
            return []
    
    async def wait_for_element_state(
        self,
        element: ElementHandle,
        state: str,
        timeout: Optional[int] = None
    ) -> bool:
        """Wait for an element to reach a specific state.
        
        Args:
            element: Element handle to wait for
            state: State to wait for (visible, hidden, stable, enabled, disabled)
            timeout: Optional timeout in milliseconds
            
        Returns:
            True if state was reached, False otherwise
        """
        try:
            await element.wait_for_element_state(
                state,
                timeout=timeout or 5000
            )
            return True
            
        except Exception as e:
            logger.warning(f"Error waiting for element state {state}: {e}")
            return False
    
    async def find_input_field(self, frame: Frame, field_name: str, field_type: str = "text") -> Optional[str]:
        """
        Find the most likely selector for an input field based on its name/label.
        
        Args:
            frame: The frame to search in
            field_name: The name/label of the field to find
            field_type: The type of input field (text, email, etc.)
            
        Returns:
            CSS selector for the field if found, None otherwise
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage(f"find_field_{field_name}")
            
        try:
            # Check cache first
            cache_key = f"{field_name}_{field_type}"
            if cache_key in self.selector_cache:
                if self.diagnostics_manager:
                    self.diagnostics_manager.end_stage(True, details={"method": "cache"})
                return self.selector_cache[cache_key]
            
            selectors = []
            
            # Try label-based selectors
            label = await frame.query_selector(f"label:text-is('{field_name}')")
            if label:
                # Check for 'for' attribute
                for_id = await label.get_attribute("for")
                if for_id:
                    selectors.append(f"#{for_id}")
                
                # Check for nested input
                input_el = await label.query_selector("input")
                if input_el:
                    input_id = await input_el.get_attribute("id")
                    if input_id:
                        selectors.append(f"#{input_id}")
            
            # Try aria-label
            selectors.extend([
                f"input[aria-label='{field_name}']",
                f"input[placeholder='{field_name}']",
                f"input[name='{field_name.lower().replace(' ', '_')}']"
            ])
            
            # Try data attributes
            selectors.extend([
                f"input[data-test='{field_name.lower().replace(' ', '-')}']",
                f"input[data-testid='{field_name.lower().replace(' ', '-')}']"
            ])
            
            # Try each selector
            for selector in selectors:
                element = await frame.query_selector(selector)
                if element:
                    # Verify it's the right type
                    el_type = await element.get_attribute("type") or "text"
                    if el_type == field_type:
                        self.selector_cache[cache_key] = selector
                        if self.diagnostics_manager:
                            self.diagnostics_manager.end_stage(True, details={
                                "method": "search",
                                "selector": selector
                            })
                        return selector
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=f"Could not find field: {field_name}",
                    details={"attempted_selectors": selectors}
                )
            return None
            
        except Error as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=str(e)
                )
            self.logger.error(f"Error finding field {field_name}: {e}")
            return None
    
    async def find_dropdown(self, frame: Frame, field_name: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Find selectors for a dropdown field and its options.
        
        Args:
            frame: The frame to search in
            field_name: The name/label of the dropdown
            
        Returns:
            Tuple of (trigger selector, options selector) or (None, None) if not found
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage(f"find_dropdown_{field_name}")
            
        try:
            # Common dropdown patterns
            trigger_patterns = [
                (f"select[aria-label='{field_name}']", "option"),
                (f"[role='combobox'][aria-label='{field_name}']", "[role='option']"),
                (f"button:text-is('{field_name}')", "[role='listbox'] [role='option']"),
                (f".select-trigger:text-is('{field_name}')", ".select-options .option")
            ]
            
            for trigger_selector, options_selector in trigger_patterns:
                trigger = await frame.query_selector(trigger_selector)
                if trigger:
                    # Verify options exist
                    await trigger.click()
                    options = await frame.query_selector(options_selector)
                    if options:
                        if self.diagnostics_manager:
                            self.diagnostics_manager.end_stage(True, details={
                                "trigger": trigger_selector,
                                "options": options_selector
                            })
                        return trigger_selector, options_selector
                    
                    # Close dropdown if opened
                    await frame.keyboard.press("Escape")
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=f"Could not find dropdown: {field_name}",
                    details={"attempted_patterns": trigger_patterns}
                )
            return None, None
            
        except Error as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=str(e)
                )
            self.logger.error(f"Error finding dropdown {field_name}: {e}")
            return None, None
    
    async def find_button(self, frame: Frame, button_text: str) -> Optional[str]:
        """Find a button by its text content."""
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage(f"find_button_{button_text}")
            
        try:
            selectors = [
                f"button:text-is('{button_text}')",
                f"[role='button']:text-is('{button_text}')",
                f"input[type='submit'][value='{button_text}']",
                f"a:text-is('{button_text}')"
            ]
            
            for selector in selectors:
                element = await frame.query_selector(selector)
                if element and await element.is_visible():
                    if self.diagnostics_manager:
                        self.diagnostics_manager.end_stage(True, details={"selector": selector})
                    return selector
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=f"Could not find button: {button_text}",
                    details={"attempted_selectors": selectors}
                )
            return None
            
        except Error as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    False,
                    error=str(e)
                )
            self.logger.error(f"Error finding button {button_text}: {e}")
            return None 