"""Tools for selecting and identifying elements in job application forms."""

import logging
from typing import Dict, Any, Optional, List, Tuple
from playwright.async_api import Frame, ElementHandle, Error
import re

from enterprise_job_agent.core.browser_interface import BrowserInterface
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager

logger = logging.getLogger(__name__)

class ElementSelector:
    """Enhanced element selection with smart waiting and retries."""
    
    def __init__(
        self,
        browser_manager,
        diagnostics_manager: Optional[DiagnosticsManager] = None
    ):
        """Initialize element selector.
        
        Args:
            browser_manager: Browser manager instance
            diagnostics_manager: Optional diagnostics manager
        """
        self.browser_manager = browser_manager
        self.diagnostics_manager = diagnostics_manager
        self.logger = logger
        self.selector_cache: Dict[str, str] = {}
    
    @property
    def frame(self):
        """Return the current page as the default frame."""
        return self.browser_manager.page
    
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
        timeout: int = 5000
    ) -> Optional[Any]:
        """Wait for an element to be available and visible.
        
        Args:
            selector: The selector to use
            frame: Optional frame to search in
            timeout: Timeout in milliseconds
        
        Returns:
            The element handle or None if not found
        """
        # Handle XPath selectors that might be prefixed incorrectly
        sanitized_selector = self._sanitize_selector(selector)
        
        context = frame or self.browser_manager.page
        try:
            element = await context.wait_for_selector(
                sanitized_selector,
                state="visible",
                timeout=timeout
            )
            if element:
                self.logger.debug(f"Found element: {sanitized_selector}")
                return element
            else:
                self.logger.debug(f"Element not visible: {sanitized_selector}")
                return None
        except Exception as e:
            self.logger.debug(f"Element not found: {sanitized_selector} - {e}")
            
            # Try alternate selector formats if this looks like an XPath expression
            if selector.startswith('#xpath=') or selector.startswith('xpath='):
                try:
                    # Extract the XPath part
                    xpath = selector.split('=', 1)[1]
                    self.logger.debug(f"Trying direct XPath: {xpath}")
                    element = await context.wait_for_selector(
                        f"xpath={xpath}",  # Ensure proper format for Playwright
                        state="visible",
                        timeout=timeout
                    )
                    if element:
                        self.logger.debug(f"Found element using XPath: {xpath}")
                        return element
                except Exception as xe:
                    self.logger.debug(f"Element not found with XPath fallback: {xe}")
                    
                    # Try one more time with stripped xpath prefix if it has extra characters
                    if xpath.startswith('/') and xpath.count('/') > 1:
                        try:
                            cleaned_xpath = xpath.strip()
                            self.logger.debug(f"Trying cleaned XPath: {cleaned_xpath}")
                            element = await context.wait_for_selector(
                                f"xpath={cleaned_xpath}",
                                state="visible",
                                timeout=timeout
                            )
                            if element:
                                self.logger.debug(f"Found element using cleaned XPath: {cleaned_xpath}")
                                return element
                        except Exception as clean_xe:
                            self.logger.debug(f"Element not found with cleaned XPath: {clean_xe}")
            
            # If it's a CSS selector with id, try a more flexible approach
            if selector.startswith('#') and not selector.startswith('#xpath='):
                try:
                    # Try with attribute selector instead of ID
                    element_id = selector[1:] # Remove the #
                    alt_selector = f"[id='{element_id}']"
                    self.logger.debug(f"Trying alternate ID selector: {alt_selector}")
                    element = await context.wait_for_selector(
                        alt_selector,
                        state="visible",
                        timeout=timeout
                    )
                    if element:
                        self.logger.debug(f"Found element using attribute selector: {alt_selector}")
                        return element
                except Exception as alt_e:
                    self.logger.debug(f"Element not found with attribute selector: {alt_e}")
            
            return None
            
    def _sanitize_selector(self, selector: str) -> str:
        """Sanitize a selector for use with Playwright.
        
        Args:
            selector: The selector to sanitize
            
        Returns:
            The sanitized selector
        """
        # Handle selectors with explicit xpath prefix
        if selector.startswith('#xpath='):
            # Remove the hash and return properly formatted xpath
            return f"xpath={selector[7:]}"
        elif selector.startswith('xpath='):
            # Already properly formatted
            return selector
            
        # Handle CSS selectors with problematic characters
        if ':' in selector and not (selector.startswith('xpath=') or selector.startswith('text=')):
            # This could be a CSS selector with pseudo-classes or a non-standard selector
            # Try to handle common cases, like :text-is or :has-text
            if 'text-is(' in selector or 'has-text(' in selector:
                # Convert to Playwright's text selector format
                for pattern, replacement in [
                    (':text-is(', ':text('),
                    (':has-text(', ':has(text=')
                ]:
                    selector = selector.replace(pattern, replacement)
                    
            # For button:text-is(\"Apply\") style selectors
            if 'button:text-is' in selector:
                # Extract the text content
                match = re.search(r'button:text-is\\(\"([^\"]+)\"\\)', selector)
                if match:
                    text = match.group(1)
                    return f'button:has-text("{text}")'
                    
        return selector

    async def find_element(self, selector: str, frame_id: Optional[str] = None, timeout: int = 10000) -> Optional[Any]:
        """
        Find an element using the given selector, with support for different frames.
        
        Args:
            selector (str): CSS selector to find the element
            frame_id (str): Optional frame ID where the element is located
            timeout (int): Maximum time to wait for the element in milliseconds
            
        Returns:
            ElementHandle or None: The found element or None if not found
        """
        try:
            sanitized_selector = self._sanitize_selector(selector)
            frame = None
            
            if self.diagnostics_manager:
                self.diagnostics_manager.debug(f"Looking for element with selector: {sanitized_selector} in frame: {frame_id}")
            
            if frame_id and frame_id != 'main':
                try:
                    frame = await self.browser_manager.get_frame(frame_id)
                    if not frame:
                        if self.diagnostics_manager:
                            self.diagnostics_manager.warning(f"Frame '{frame_id}' not found. Falling back to main frame.")
                except Exception as e:
                    if self.diagnostics_manager:
                        self.diagnostics_manager.error(f"Error getting frame '{frame_id}': {str(e)}")
            
            if not frame:
                frame = self.browser_manager.page
            
            # First try the exact selector
            try:
                element = await frame.wait_for_selector(sanitized_selector, timeout=timeout)
                if element:
                    if self.diagnostics_manager:
                        self.diagnostics_manager.debug(f"Found element with selector: {sanitized_selector}")
                    return element
            except Exception as e:
                if self.diagnostics_manager:
                    self.diagnostics_manager.debug(f"Failed to find element with exact selector '{sanitized_selector}': {str(e)}")
            
            # Try alternatives
            alternative_selectors = self._generate_alternative_selectors(sanitized_selector)
            for alt_selector in alternative_selectors:
                try:
                    element = await frame.wait_for_selector(alt_selector, timeout=timeout/2)  # Use shorter timeout for alternatives
                    if element:
                        if self.diagnostics_manager:
                            self.diagnostics_manager.debug(f"Found element with alternative selector: {alt_selector}")
                        return element
                except Exception as e:
                    if self.diagnostics_manager:
                        self.diagnostics_manager.debug(f"Failed to find element with alternative selector '{alt_selector}': {str(e)}")
            
            if self.diagnostics_manager:
                self.diagnostics_manager.warning(f"Element not found with selector: {sanitized_selector} or its alternatives")
            return None
        
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.error(f"Error in find_element: {str(e)}")
            return None

    def _generate_alternative_selectors(self, selector):
        """Generate alternative selectors to try if the primary selector fails."""
        alternatives = []
        
        # If selector is an ID selector, try by name attribute
        if selector.startswith('#'):
            name_selector = f"[name='{selector[1:]}']"
            alternatives.append(name_selector)
            
            # Also try with data-id attribute
            data_id_selector = f"[data-id='{selector[1:]}']"
            alternatives.append(data_id_selector)
            
            # Try with role=combobox for dropdowns
            role_selector = f"[role='combobox'][id='{selector[1:]}']"
            alternatives.append(role_selector)
            
        # For very specific selectors, try more generic alternatives
        if ' ' in selector:
            simpler_selector = selector.split(' ')[-1]
            alternatives.append(simpler_selector)
            
        return alternatives

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
            context = frame or self.browser_manager.page
            if not context:
                logger.error("No valid context (frame or page) available")
                return []
            
            # Find all matching elements
            elements = await context.query_selector_all(selector)
            return elements
            
        except Exception as e:
            logger.warning(f"Error finding elements {selector}: {e}")
            return []
    
    async def find_element_by_text(
        self,
        text_content: str,
        frame: Optional[Frame] = None,
        element_type: str = "*",
        exact_match: bool = False,
        visible: bool = True,
        timeout: int = 3000
    ) -> Optional[ElementHandle]:
        """Find an element based on its visible text content.

        Args:
            text_content: The text content to search for.
            frame: Optional frame to search in. Defaults to the main page.
            element_type: Optional element tag to restrict the search (e.g., 'button', 'input'). Defaults to '*'.
            exact_match: Whether to perform an exact text match (case-sensitive). Defaults to False (substring match).
            visible: Whether the element must be visible. Defaults to True.
            timeout: Timeout in milliseconds. Defaults to 3000.

        Returns:
            ElementHandle if found, None otherwise.
        """
        if self.diagnostics_manager:
            stage_name = f"find_element_by_text_{element_type}_{'exact' if exact_match else 'contains'}_{text_content[:20]}"
            self.diagnostics_manager.start_stage(stage_name)

        try:
            context = frame or self.browser_manager.page
            if not context:
                logger.error("No valid context (frame or page) available for text search.")
                if self.diagnostics_manager:
                    self.diagnostics_manager.end_stage(False, error="No valid context")
                return None

            # Construct the Playwright text selector
            if exact_match:
                selector = f"{element_type}:text-is(\"{text_content}\")"
            else:
                # Escape quotes within the text content for the selector
                escaped_text = text_content.replace('"', '\\"')
                selector = f"{element_type}:text(\"{escaped_text}\")"

            logger.debug(f"Attempting to find element with text selector: {selector}")

            # Use wait_for_selector to find the element based on text
            element = await context.wait_for_selector(
                selector,
                state="visible" if visible else "attached",
                timeout=timeout
            )

            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(True)
            return element

        except Error as e:
            # More specific Playwright error handling can be added here if needed
            logger.debug(f"Element with text '{text_content}' not found using selector '{selector}'. Error: {e}")
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=str(e))
            return None
        except Exception as e:
            logger.error(f"Unexpected error finding element by text '{text_content}': {e}")
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=f"Unexpected error: {str(e)}")
            return None
    
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

    async def detect_element_type(self, selector: str, frame: Optional[Any] = None) -> Dict[str, Any]:
        """
        Detect the type and features of an element.
        
        Args:
            selector: The CSS or XPath selector
            frame: Optional frame to search in
            
        Returns:
            Dictionary with element type information
        """
        result = {
            'is_react_select': False,
            'is_typeahead': False,
            'is_custom_dropdown': False,
            'component_info': {}
        }
        
        try:
            # Handle XPath selectors properly
            if selector.startswith('xpath='):
                # This is a direct XPath selector
                xpath = selector[6:]  # Remove 'xpath=' prefix
                context = frame if frame else self.browser_manager.page
                
                # Use evaluate to safely detect element type with XPath
                js_detect = f"""
                () => {{
                    try {{
                        const element = document.evaluate("{xpath}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (!element) return {{"exists": false}};
                        
                        const info = {{
                            "exists": true,
                            "tag_name": element.tagName.toLowerCase(),
                            "input_type": element.getAttribute("type"),
                            "aria_role": element.getAttribute("role"),
                            "classes": element.className,
                            "has_placeholder": !!element.getAttribute("placeholder"),
                            "container_id": element.parentElement ? element.parentElement.id : "",
                            "container_class": element.parentElement ? element.parentElement.className : ""
                        }};
                        
                        // Check for common react-select patterns
                        const isReactSelect = 
                            element.className.includes("select__input") || 
                            (element.parentElement && element.parentElement.className.includes("select__")) ||
                            document.querySelector(".select__menu, .select__menu-list, .select__option") !== null;
                            
                        return {{...info, "is_react_select": isReactSelect}};
                    }} catch (e) {{
                        return {{"error": e.toString()}};
                    }}
                }}
                """
                info = await context.evaluate(js_detect)
                
                if info.get("exists", False):
                    result["component_info"] = info
                    result["is_react_select"] = info.get("is_react_select", False)
                    result["is_typeahead"] = (
                        info.get("aria_role") == "combobox" or
                        (info.get("tag_name") == "input" and info.get("is_react_select"))
                    )
                    result["is_custom_dropdown"] = result["is_react_select"]
                
                return result
                
            # Handle CSS selectors
            context = frame if frame else self.browser_manager.page
            element = await context.query_selector(selector)
            
            if not element:
                self.logger.debug(f"Element not found for type detection: {selector}")
                return result
            
            # Get basic element info
            tag_name = await (await element.get_property('tagName')).json_value()
            component_info = {
                'tag_name': tag_name.lower(),
            }
            
            # Add more details for input elements
            if tag_name.lower() == 'input':
                input_type = await element.get_attribute('type') or 'text'
                aria_role = await element.get_attribute('role')
                classes = await element.get_attribute('class') or ''
                
                component_info.update({
                    'input_type': input_type,
                    'aria_role': aria_role,
                    'classes': classes,
                    'has_placeholder': await element.get_attribute('placeholder') is not None
                })
                
                # Check container for React or custom select components
                js_check_container = """
                (element) => {
                    const parent = element.parentElement;
                    return {
                        container_id: parent ? parent.id : '',
                        container_class: parent ? parent.className : '',
                        has_select_container: parent ? 
                            parent.className.includes('select__') || 
                            document.querySelector('.select__menu, .select__menu-list, .select__option') !== null 
                            : false
                    };
                }
                """
                container_info = await element.evaluate(js_check_container)
                component_info.update(container_info)
                
                # Detect React Select component
                result['is_react_select'] = (
                    'select__input' in classes or
                    container_info.get('has_select_container', False) or
                    container_info.get('container_class', '').find('select__') >= 0
                )
                
                # Detect typeahead behavior
                result['is_typeahead'] = (
                    aria_role == 'combobox' or
                    result['is_react_select'] or
                    classes.find('autocomplete') >= 0 or
                    await element.get_attribute('autocomplete') == 'off'
                )
                
                # Detect custom dropdown
                result['is_custom_dropdown'] = result['is_react_select']
            
            result['component_info'] = component_info
            return result
            
        except Exception as e:
            self.logger.debug(f"Error detecting element type for {selector}: {str(e)}")
            return result
            
    async def get_options_for_element(self, selector: str, frame = None) -> list:
        """Get available options for a dropdown or combobox element.
        
        Args:
            selector: CSS selector for the element
            frame: Optional frame to search in
            
        Returns:
            List of option text values
        """
        try:
            if self.diagnostics_manager:
                self.diagnostics_manager.start_stage(f"get_options_{selector}")
            
            context = frame or self.browser_manager.page
            element = await self.wait_for_element(selector, frame)
            if not element:
                if self.diagnostics_manager:
                    self.diagnostics_manager.end_stage(False, error="Element not found")
                return []
            
            # First attempt: Try native select options
            try:
                tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                if tag_name == "select":
                    options = await element.evaluate("""
                        select => Array.from(select.options).map(option => option.text)
                    """)
                    if options and len(options) > 0:
                        if self.diagnostics_manager:
                            self.diagnostics_manager.end_stage(
                                True, 
                                details={"method": "native_select", "count": len(options)}
                            )
                        return options
            except Exception as e:
                self.logger.debug(f"Native select options extraction failed: {e}")
            
            # Second attempt: Use comprehensive JavaScript approach for advanced options detection
            try:
                options = await self._extract_options_with_javascript(context)
                if options and len(options) > 0:
                    if self.diagnostics_manager:
                        self.diagnostics_manager.end_stage(
                            True, 
                            details={"method": "comprehensive_js", "count": len(options)}
                        )
                    return options
            except Exception as e:
                self.logger.debug(f"Comprehensive JS options extraction failed: {e}")
            
            # Third attempt: Try DOM-based extraction for common patterns
            try:
                options = await self._extract_options_from_dom(context, selector)
                if options and len(options) > 0:
                    if self.diagnostics_manager:
                        self.diagnostics_manager.end_stage(
                            True, 
                            details={"method": "dom_extraction", "count": len(options)}
                        )
                    return options
            except Exception as e:
                self.logger.debug(f"DOM-based options extraction failed: {e}")
            
            # If no options found, return empty list
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error="No options found")
            return []
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=str(e))
            self.logger.error(f"Error getting options for {selector}: {e}")
            return []

    async def _extract_options_with_javascript(self, context) -> list:
        """Extract dropdown options using comprehensive JavaScript.
        
        This uses a sophisticated approach that can detect options across various
        dropdown, combobox, and typeahead implementations.
        
        Args:
            context: Page or frame context
            
        Returns:
            List of option text values
        """
        js_code = """
        () => {
            // Collect all possible options from the page
            const results = new Set();
            
            // Common dropdown option selectors
            const selectors = [
                '[role="option"]', 
                'li[data-option]', 
                '.option', 
                '.dropdown-item',
                'li:not([style*="display: none"])',
                'div[role="listitem"]',
                '.Select-option',
                '.autocomplete-option',
                '.typeahead-option',
                '.select__option',
                '.listbox__option',
                '.ui-menu-item',
                'ul.dropdown-menu li',
                '.MuiAutocomplete-option',
                '.react-select__option',
                'option',
                '[role="listbox"] > *'
            ];
            
            // Process visible elements that match our selectors
            for (const selector of selectors) {
                const elements = document.querySelectorAll(selector);
                for (const el of elements) {
                    // Check if element is visible (approximately)
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const isVisible = rect.width > 0 && 
                                    rect.height > 0 && 
                                    style.display !== 'none' && 
                                    style.visibility !== 'hidden';
                    
                    if (isVisible) {
                        // Get text content, removing extra whitespace
                        const text = el.textContent.trim().replace(/\\s+/g, ' ');
                        if (text && text.length > 0) {
                            results.add(text);
                        }
                        
                        // Also check for value or data attributes that might contain the option value
                        const valueAttrs = ['value', 'data-value', 'data-option-value', 'data-display-value'];
                        for (const attr of valueAttrs) {
                            const value = el.getAttribute(attr);
                            if (value && value.trim() && value.trim().length > 0) {
                                results.add(value.trim());
                            }
                        }
                    }
                }
            }
            
            // Handle specialized frameworks
            
            // React-Select
            const reactSelectOptions = document.querySelectorAll('[class*="react-select__option"]');
            reactSelectOptions.forEach(option => {
                const text = option.textContent.trim();
                if (text) results.add(text);
            });
            
            // Material UI
            const muiOptions = document.querySelectorAll('[class*="MuiAutocomplete-option"]');
            muiOptions.forEach(option => {
                const text = option.textContent.trim();
                if (text) results.add(text);
            });
            
            // Convert Set to Array and return
            return Array.from(results);
        }
        """
        
        try:
            options = await context.evaluate(js_code)
            return options if options else []
        except Exception as e:
            self.logger.debug(f"JavaScript option extraction failed: {e}")
            return []

    async def _extract_options_from_dom(self, context, selector) -> list:
        """Extract dropdown options through DOM traversal.
        
        Args:
            context: Page or frame context
            selector: Original selector that triggered the dropdown
            
        Returns:
            List of option text values
        """
        options = []
        
        # Common selectors for dropdown options
        option_selectors = [
            'li',
            'div[role="option"]',
            '[role="option"]',
            '.dropdown-item',
            '.option',
            'option'
        ]
        
        for option_selector in option_selectors:
            try:
                elements = await context.query_selector_all(option_selector)
                for element in elements:
                    try:
                        is_visible = await element.is_visible()
                        if is_visible:
                            text = await element.text_content()
                            if text and text.strip():
                                options.append(text.strip())
                    except Exception:
                        continue
            except Exception:
                continue
        
        # Remove duplicates while preserving order
        unique_options = []
        for option in options:
            if option not in unique_options:
                unique_options.append(option)
        
        return unique_options

    async def get_element(self, selector: str, frame: Optional[Any] = None) -> Optional[ElementHandle]:
        """
        Get an element by selector.
        
        Args:
            selector: The CSS or XPath selector
            frame: Optional frame to search in
            
        Returns:
            ElementHandle if found, None otherwise
        """
        try:
            # Handle XPath selectors
            if selector.startswith('xpath='):
                xpath = selector[6:]  # Remove 'xpath=' prefix
                context = frame if frame else self.browser_manager.page
                element = await context.wait_for_selector(f"xpath={xpath}", timeout=3000)
                return element
            # Handle CSS selectors
            else:
                context = frame if frame else self.browser_manager.page
                element = await context.query_selector(selector)
                return element
        except Exception as e:
            self.logger.debug(f"Error finding element {selector}: {str(e)}")
            return None

    async def generate_stable_selector(self, element_handle: ElementHandle, frame: Frame) -> Optional[str]:
        """Generates the most stable selector possible for a given element handle.
        
        Prioritizes:
        1. data-testid, data-qa, data-cy
        2. Unique ID
        3. Unique Name
        4. Role + Accessible Name (aria-label, text)
        5. Placeholder + Tag/Type
        6. Text Content (if unique and short enough)
        7. Class + Tag (if reasonably unique)
        8. CSS Path (as a last resort)
        
        Args:
            element_handle: The Playwright ElementHandle to generate a selector for.
            frame: The Playwright Frame containing the element (needed for uniqueness checks).
            
        Returns:
            A stable CSS selector string or None if generation fails.
        """
        if not element_handle or not frame:
            return None
            
        try:
            # --- Strategy 1: Test IDs ---
            test_ids = ['data-testid', 'data-qa', 'data-cy', 'data-test-id']
            for test_id_attr in test_ids:
                test_id_value = await element_handle.get_attribute(test_id_attr)
                if test_id_value:
                    selector = f"[{test_id_attr}='{test_id_value}']"
                    if await self._is_selector_unique(frame, selector):
                        self.logger.debug(f"Generated stable selector using {test_id_attr}: {selector}")
                        return selector
                        
            # --- Strategy 2: Unique ID --- 
            element_id = await element_handle.get_attribute("id")
            if element_id:
                 # Basic validation: Not just a number, reasonable length
                 if not element_id.isdigit() and len(element_id) > 2: 
                    selector = f"#{element_id}" # Use direct ID selector
                    # Normalize potentially problematic ID characters
                    normalized_selector = await self._normalize_selector(selector)
                    if await self._is_selector_unique(frame, normalized_selector):
                         self.logger.debug(f"Generated stable selector using unique ID: {normalized_selector}")
                         return normalized_selector
                             
            # --- Strategy 3: Unique Name --- 
            name = await element_handle.get_attribute("name")
            tag_name = (await element_handle.evaluate("el => el.tagName.toLowerCase()")) or ""
            if name:
                 selector = f"{tag_name}[name='{name}']"
                 if await self._is_selector_unique(frame, selector):
                     self.logger.debug(f"Generated stable selector using unique Name: {selector}")
                     return selector
                     
            # --- Strategy 4: Role + Accessible Name --- 
            role = await element_handle.get_attribute("role")
            aria_label = await element_handle.get_attribute("aria-label")
            text_content = (await element_handle.text_content() or "").strip()
            acc_name = aria_label or text_content
            
            if role and acc_name and len(acc_name) < 50: # Use accessible name if reasonably short
                # Simple text match first
                # Ensure the embedded string is properly escaped and the f-string is valid
                # Use double quotes for the outer f-string and single quotes inside, or vice-versa
                # Escape quotes within the has-text content
                escaped_acc_name = self._escape_css_string(acc_name)
                selector = f'{tag_name}[role="{role}"]:has-text("{escaped_acc_name}")'
                if await self._is_selector_unique(frame, selector):
                    self.logger.debug(f"Generated stable selector using Role + Accessible Name: {selector}")
                    return selector
                # Maybe try with aria-label attribute specifically
                if aria_label:
                    escaped_aria_label = self._escape_css_string(aria_label)
                    selector = f'{tag_name}[role="{role}"][aria-label="{escaped_aria_label}"]'
                    if await self._is_selector_unique(frame, selector):
                         self.logger.debug(f"Generated stable selector using Role + aria-label: {selector}")
                         return selector
                         
            # --- Strategy 5: Placeholder + Tag/Type --- 
            if tag_name in ["input", "textarea"]:
                 placeholder = await element_handle.get_attribute("placeholder")
                 input_type = await element_handle.get_attribute("type")
                 if placeholder:
                     selector_parts = [tag_name]
                     if input_type: selector_parts.append(f"[type='{input_type}']")
                     selector_parts.append(f"[placeholder='{self._escape_css_string(placeholder)}']")
                     selector = "".join(selector_parts)
                     if await self._is_selector_unique(frame, selector):
                          self.logger.debug(f"Generated stable selector using Placeholder: {selector}")
                          return selector
                          
            # --- Strategy 6: Text Content --- 
            # Useful for buttons, links, headers, etc.
            if tag_name in ["button", "a", "label", "span", "h1", "h2", "h3", "h4", "div"] and text_content and len(text_content) < 50:
                selector = f'{tag_name}:has-text(\'{self._escape_css_string(text_content)}\')'
                if await self._is_selector_unique(frame, selector):
                     self.logger.debug(f"Generated stable selector using Text Content: {selector}")
                     return selector
                     
            # --- Strategy 7: Class + Tag (if reasonably unique) --- 
            # Less stable, use with caution
            class_name = await element_handle.get_attribute("class")
            if class_name:
                # Try using the first class if it seems specific enough
                first_class = class_name.split()[0]
                # Avoid generic classes
                if first_class and not any(g in first_class for g in ['form-', 'input-', 'control', 'field', 'wrapper', 'container']): 
                    selector = f"{tag_name}.{first_class}"
                    count = await frame.locator(selector).count()
                    if count == 1:
                         self.logger.debug(f"Generated potentially stable selector using first Class: {selector}")
                         return selector
            
            # --- Strategy 8: CSS Path (Fallback) --- 
            # Playwright can generate this, but let's try a basic JS version first
            try:
                path_selector = await element_handle.evaluate(r"""el => {
                    let path = '';
                    let current = el;
                    while (current && current.tagName !== 'BODY') {
                        let selector = current.tagName.toLowerCase();
                        const id = current.id;
                        if (id && !id.match(/^\d/)) { // Use ID if valid and not starting with digit
                            selector = `#${id}`;
                            path = selector + (path ? ' > ' + path : '');
                            break; // Stop if ID is found
                        }
                        // Add nth-child/of-type for disambiguation
                        const parent = current.parentElement;
                        if (parent) {
                            const siblings = Array.from(parent.children);
                            const sameTagSiblings = siblings.filter(sibling => sibling.tagName === current.tagName);
                            if (sameTagSiblings.length > 1) {
                                const index = sameTagSiblings.indexOf(current) + 1;
                                selector += `:nth-of-type(${index})`;
                            }
                        }
                        path = selector + (path ? ' > ' + path : '');
                        current = parent;
                    }
                    return path ? 'body > ' + path : null; 
                }""")
                if path_selector and await self._is_selector_unique(frame, path_selector):
                    self.logger.debug(f"Generated fallback CSS Path selector: {path_selector}")
                    return path_selector
            except Exception as path_ex:
                 self.logger.warning(f"Failed to generate CSS path: {path_ex}")

            self.logger.warning(f"Could not generate a stable unique selector for the element.")
            # Optionally return the least stable selector generated (e.g., tag name) as absolute fallback?
            return None 

        except Exception as e:
            self.logger.error(f"Error generating stable selector: {e}", exc_info=True)
            return None
            
    async def _is_selector_unique(self, frame: Frame, selector: str) -> bool:
        """Checks if a selector uniquely identifies one element in the frame."""
        try:
            count = await frame.locator(selector).count()
            is_unique = count == 1
            if not is_unique:
                 self.logger.debug(f"Selector '{selector}' is not unique (count: {count}).")
            return is_unique
        except Exception as e:
            # Invalid selector syntax or other error
            self.logger.debug(f"Error checking selector uniqueness for '{selector}': {e}")
            return False
            
    def _escape_css_string(self, value: str) -> str:
        """Escapes characters unsafe for CSS string literals."""
        if not value:
            return ""
        # Basic escaping for quotes
        return value.replace('"', '\\"').replace("'", "\\'")

    def _generate_alternative_selectors(self, selector):
        """Generate alternative selectors based on the provided one."""
        alternatives = []
        
        # If selector is an ID selector, try by name attribute
        if selector.startswith('#'):
            name_selector = f"[name='{selector[1:]}']"
            alternatives.append(name_selector)
            
            # Also try with data-id attribute
            data_id_selector = f"[data-id='{selector[1:]}']"
            alternatives.append(data_id_selector)
            
            # Try with role=combobox for dropdowns
            role_selector = f"[role='combobox'][id='{selector[1:]}']"
            alternatives.append(role_selector)
            
        # For very specific selectors, try more generic alternatives
        if ' ' in selector:
            simpler_selector = selector.split(' ')[-1]
            alternatives.append(simpler_selector)
            
        return alternatives 

    async def _get_relevant_aria_attributes(self, element_handle: ElementHandle) -> Dict[str, str]:
        """Extracts relevant ARIA attributes from an element handle."""
        aria_attributes = {}
        try:
            # List of ARIA attributes we care about
            relevant_aria = [
                'aria-label', 'aria-labelledby', 'aria-describedby',
                'aria-required', 'aria-invalid', 'aria-disabled',
                'aria-expanded', 'aria-haspopup', 'aria-controls',
                'aria-owns', 'aria-activedescendant', 'aria-live',
                'aria-atomic', 'aria-busy', 'aria-checked',
                'aria-current', 'aria-hidden', 'aria-modal', 
                'aria-multiline', 'aria-multiselectable', 'aria-orientation',
                'aria-placeholder', 'aria-pressed', 'aria-readonly', 
                'aria-selected', 'aria-sort', 'aria-valuemax', 
                'aria-valuemin', 'aria-valuenow', 'aria-valuetext'
            ]
            
            # Use evaluate to get multiple attributes efficiently
            attributes = await element_handle.evaluate(
                """(element, relevant_aria) => {
                    const attrs = {};
                    for (const attr of relevant_aria) {
                        const value = element.getAttribute(attr);
                        if (value !== null) { // Only include attributes that exist
                            attrs[attr] = value;
                        }
                    }
                    return attrs;
                }""", relevant_aria
            )
            aria_attributes = attributes if attributes else {}

        except Exception as e:
            # Log the error but don't crash the whole process
            self.logger.debug(f"Could not extract ARIA attributes: {e}")
            aria_attributes = {} # Return empty dict on error
            
        return aria_attributes 