"""Action executor for job application system."""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass
import os
import difflib
import re

from enterprise_job_agent.core.browser_manager import BrowserManager
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.tools.element_selector import ElementSelector

logger = logging.getLogger(__name__)

@dataclass
class ActionContext:
    """Context for an action execution."""
    field_id: str
    field_type: str
    field_value: Any
    frame_id: Optional[str] = None
    options: Optional[Dict[str, Any]] = None

class ActionExecutor:
    """Executor for web form actions like filling fields, selecting from dropdowns, etc.
    
    In test mode, this simulates the actions without actually performing them.
    In production mode, this would control the browser via Playwright.
    """
    
    browser_manager: Optional[BrowserManager]
    logger: logging.Logger
    test_mode: bool
    max_retries: int
    retry_delay: int
    diagnostics_manager: Optional[DiagnosticsManager]
    form_interaction: Optional[FormInteraction]
    
    def __init__(self, browser_manager: Optional[BrowserManager] = None, logger: Optional[logging.Logger] = None):
        """Initialize the action executor.
        
        Args:
            browser_manager: Optional browser manager to use for actions
            logger: Optional logger to use
        """
        self.browser_manager = browser_manager
        self.logger = logger or logging.getLogger(__name__)
        self.test_mode = True  # Default to test mode for safety
        self.max_retries = 3   # Default number of retries
        self.retry_delay = 1   # Default delay between retries (seconds)
        self.diagnostics_manager = None  # Will be set externally if needed
        self.form_interaction = None  # Will be set if needed
    
    def set_diagnostics_manager(self, diagnostics_manager):
        """Set the diagnostics manager.
        
        Args:
            diagnostics_manager: DiagnosticsManager instance
        """
        self.diagnostics_manager = diagnostics_manager
        
    def set_form_interaction(self, form_interaction):
        """Set the form interaction helper.
        
        Args:
            form_interaction: FormInteraction instance
        """
        self.form_interaction = form_interaction
    
    def set_test_mode(self, test_mode: bool = True):
        """Set the test mode flag.
        
        Args:
            test_mode: Whether to run in test mode
        """
        self.test_mode = test_mode
        self.logger.info(f"ActionExecutor set to {'test' if test_mode else 'production'} mode")
    
    async def execute_action(
        self, 
        action_type: str, 
        selector: str,
        value: Any = None,
        frame_id: Optional[str] = None
    ) -> bool:
        """Execute an action on a web element.
        
        Args:
            action_type: Type of action (fill, select, checkbox, click, upload)
            selector: CSS selector for the element
            value: Value to set (if applicable)
            frame_id: Frame ID if the element is in a frame
            
        Returns:
            Success flag
        """
        self.logger.info(f"Executing {action_type} on {selector} with value {value}")
        
        if self.test_mode:
            # In test mode, we just log and pretend it worked
            self.logger.info(f"TEST MODE: Simulating {action_type} on {selector} with value {value}")
            return True
        
        # In production mode, we would execute the actual browser action
        try:
            if action_type == "fill":
                return await self._execute_fill_action(selector, value, frame_id)
            elif action_type == "select":
                return await self._execute_select_action(selector, value, frame_id)
            elif action_type == "checkbox":
                return await self._set_checkbox(selector, value, frame_id)
            elif action_type == "click":
                return await self._execute_click_action(selector, frame_id)
            elif action_type == "upload":
                return await self._execute_file_action(selector, value, frame_id)
            else:
                self.logger.error(f"Unknown action type: {action_type}")
                return False
        except Exception as e:
            self.logger.error(f"Error executing {action_type} on {selector}: {str(e)}")
            return False
    
    async def _execute_fill_action(
        self, 
        selector: str, 
        value: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Execute a fill action."""
        try:
            if self.test_mode:
                self.logger.info(f"TEST MODE: Simulating fill on {selector} with value {value}")
                return True
            
            # Get the page from browser_manager
            page = self.browser_manager.get_page()
            
            # Get appropriate frame
            frame = await self._get_frame(frame_id)
            
            # Sanitize the selector if it's numeric
            safe_selector = self._sanitize_selector(selector)
            
            # Clear existing value first (if any)
            await frame.evaluate(f"""(selector) => {{
                const element = document.querySelector(selector);
                if (element) {{
                    element.value = '';
                }}
            }}""", safe_selector)
                
            # Fill the field
            await frame.fill(safe_selector, value)
            
            return True
        except Exception as e:
            self.logger.error(f"Error filling text in {selector}: {str(e)}")
            return False
            
    def _get_variation_seed(self, value=None, selector=None):
        """Generate a deterministic but varied seed value for timing variations.
        
        This makes interactions appear more human-like while keeping them
        deterministic for debugging purposes.
        
        Args:
            value: Optional value to include in seed generation
            selector: Optional selector to include in seed generation
            
        Returns:
            Integer for use in timing variations
        """
        # Combine values for a unique but deterministic seed
        seed_str = f"{value or ''}_{selector or ''}_{id(self)}"
        # Use hash for deterministic "randomness"
        return abs(hash(seed_str))
        
    async def _execute_select_action(
        self, 
        selector: str, 
        value: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Execute a select dropdown action.
        
        Uses a methodical, controlled approach to handle various dropdown types.
        
        Args:
            selector: CSS selector for the element
            value: Value to select
            frame_id: Frame ID if element is in a frame
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.test_mode:
                self.logger.info(f"TEST MODE: Simulating select on {selector} with value {value}")
                return True
            
            # Skip if the value is "N/A" or empty
            if not value or value.lower() == "n/a":
                self.logger.warning(f"Skipping selection for {selector} with placeholder value: {value}")
                return False
            
            # Get appropriate frame
            frame = await self._get_frame(frame_id)
            
            # Sanitize selector if it's numeric
            safe_selector = self._sanitize_selector(selector)
            
            # First, try to get available options to find best match
            available_options = await self._get_dropdown_options(frame, safe_selector)
            self.logger.debug(f"Available options for {selector}: {available_options}")
            
            # Find best match if we have options
            if available_options:
                best_match = self._find_best_match(value, available_options)
                if best_match:
                    self.logger.info(f"Found best match for '{value}': '{best_match}'")
                    value = best_match
            
            # Clean up any previous dropdown state
            await self._cleanup_dropdown_state(frame)
            
            # Vary the interaction pattern based on field and value to avoid predictable patterns
            # This makes bot detection harder
            variation = self._get_variation_seed(value, selector) % 3
            
            if variation == 0:
                # Strategy 1: Standard HTML select
                try:
                    if await self._try_standard_select(frame, safe_selector, value):
                        return True
                except Exception as e:
                    self.logger.debug(f"Standard select failed: {str(e)}")
                
                # Fall back to simple dropdown
                try:
                    if await self._try_simple_dropdown(frame, safe_selector, value):
                        return True
                except Exception as e:
                    self.logger.debug(f"Simple dropdown approach failed: {str(e)}")
                
            elif variation == 1:
                # Strategy 2: Try simple click-type-enter approach first
                try:
                    if await self._try_simple_dropdown(frame, safe_selector, value):
                        return True
                except Exception as e:
                    self.logger.debug(f"Simple dropdown approach failed: {str(e)}")
                
                # Then try standard select
                try:
                    if await self._try_standard_select(frame, safe_selector, value):
                        return True
                except Exception as e:
                    self.logger.debug(f"Standard select failed: {str(e)}")
                
            else:  # variation == 2
                # Strategy 3: Go straight to advanced dropdown handling
                pass
            
            # Always try advanced approach as last resort
            try:
                if await self._try_advanced_dropdown(frame, safe_selector, value):
                    return True
            except Exception as e:
                self.logger.debug(f"Advanced dropdown approach failed: {str(e)}")
            
            # Always clean up any potential open dropdowns
            await self._cleanup_dropdown_state(frame)
            
            self.logger.warning(f"All dropdown selection methods failed for {selector}")
            return False
            
        except Exception as e:
            self.logger.error(f"Error selecting from dropdown {selector}: {str(e)}")
            
            # Try to cleanup any open dropdowns
            try:
                frame = await self._get_frame(frame_id)
                await self._cleanup_dropdown_state(frame)
            except Exception:
                pass
                
            return False
            
    async def _cleanup_dropdown_state(self, frame):
        """Clean up any open dropdown or dialog state using human-like interactions.
        
        This uses varied techniques to avoid detection patterns and ensure
        dropdowns are properly closed.
        
        Args:
            frame: The frame to clean up in
        """
        try:
            # Approach 1: Try Escape key first (common human interaction)
            try:
                await frame.keyboard.press("Escape")
                await frame.wait_for_timeout(50 + (self._get_variation_seed() % 100))
            except Exception as e:
                self.logger.debug(f"Escape key press failed during cleanup: {str(e)}")
                # Continue to next approach
            
            # Check if dropdowns are still visible
            try:
                dropdowns_visible = await frame.evaluate("""() => {
                    const containers = document.querySelectorAll('div[class*="menu"], ul[class*="menu"], div[class*="dropdown"], div[class*="list"]');
                    for (const container of containers) {
                        if (container.offsetParent !== null) {
                            return true;
                        }
                    }
                    return false;
                }""")
            except Exception as e:
                self.logger.debug(f"Dropdown visibility check failed: {str(e)}")
                # Assume dropdowns might be visible and try to clean up anyway
                dropdowns_visible = True
            
            if dropdowns_visible:
                # Approach 2: Click away from the dropdown (vary the click location)
                try:
                    variation = self._get_variation_seed() % 4
                    if variation == 0:
                        # Click top-left
                        await frame.click("body", position={"x": 5, "y": 5})
                    elif variation == 1:
                        # Click near the center
                        body_size = await frame.evaluate("""() => {
                            return {
                                width: document.body.clientWidth,
                                height: document.body.clientHeight
                            };
                        }""")
                        center_x = body_size.get("width", 500) // 2
                        center_y = body_size.get("height", 500) // 2
                        await frame.click("body", position={"x": center_x, "y": center_y})
                    else:
                        # Click somewhere else with slight randomness
                        x_pos = 10 + (self._get_variation_seed() % 50)
                        y_pos = 10 + (self._get_variation_seed("y") % 50)
                        await frame.click("body", position={"x": x_pos, "y": y_pos})
                    
                    await frame.wait_for_timeout(50 + (self._get_variation_seed() % 100))
                except Exception as e:
                    self.logger.debug(f"Click away from dropdown failed: {str(e)}")
                    # Continue to next approach
                
                # Check again and try Tab key if still open
                try:
                    dropdowns_visible = await frame.evaluate("""() => {
                        const containers = document.querySelectorAll('div[class*="menu"], ul[class*="menu"], div[class*="dropdown"], div[class*="list"]');
                        for (const container of containers) {
                            if (container.offsetParent !== null) {
                                return true;
                            }
                        }
                        return false;
                    }""")
                except Exception as e:
                    self.logger.debug(f"Second dropdown visibility check failed: {str(e)}")
                    # Assume dropdowns might still be visible
                    dropdowns_visible = True
                
                if dropdowns_visible:
                    # Approach 3: Try Tab key to move focus away
                    try:
                        await frame.keyboard.press("Tab")
                        await frame.wait_for_timeout(70)
                    except Exception as e:
                        self.logger.debug(f"Tab key press failed during cleanup: {str(e)}")
                        # Continue to final approach
                    
                    # Final fallback: JavaScript forced blur
                    try:
                        await frame.evaluate("""() => {
                            // Make sure nothing is actively focused
                            if (document.activeElement) {
                                document.activeElement.blur();
                            }
                            
                            // Force any visible dropdowns to hide by clicking away
                            const containers = document.querySelectorAll('div[class*="menu"], ul[class*="menu"], div[class*="dropdown"], div[class*="list"]');
                            for (const container of containers) {
                                if (container.offsetParent !== null) {
                                    // Try to hide by setting display:none to fully close
                                    container.style.display = 'none';
                                }
                            }
                        }""")
                    except Exception as e:
                        self.logger.debug(f"JavaScript forced blur failed: {str(e)}")
                        # We've tried our best at this point
        except Exception as e:
            self.logger.debug(f"Dropdown cleanup error (non-critical): {str(e)}")
        
        # Regardless of errors, always try one final pause to let any UI reactions complete
        try:
            await frame.wait_for_timeout(70 + (self._get_variation_seed() % 50))
        except Exception:
            pass
            
    async def _try_simple_dropdown(self, frame, selector: str, value: str) -> bool:
        """Try a simple and controlled approach for dropdown selection with human-like behavior.
        
        Args:
            frame: The frame to interact with
            selector: CSS selector for the element
            value: Value to select
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # 1. Click to open the dropdown with variable timing (more human-like)
            await frame.click(selector)
            
            # Variable wait time (250-500ms) to mimic human behavior
            wait_time = 250 + (hash(value) % 250)  # Deterministic but variable based on input
            await frame.wait_for_timeout(wait_time)
            
            # 2. Clear any existing text
            await frame.fill(selector, "")
            
            # Small pause before typing (50-150ms)
            await frame.wait_for_timeout(50 + (hash(selector) % 100))
            
            # 3. Type the value with natural timing
            if len(value) > 3:
                # For longer inputs, type first few chars, pause, then complete
                halfway = len(value) // 2
                await frame.fill(selector, value[:halfway])
                await frame.wait_for_timeout(150 + (hash(value) % 200))  # Variable pause
                await frame.fill(selector, value)
            else:
                # For short inputs, just type directly
                await frame.fill(selector, value)
            
            # Pause to let dropdown suggestions appear
            await frame.wait_for_timeout(300 + (hash(value) % 150))
            
            # 4. Now look for exact matching options first via JS
            option_clicked = await frame.evaluate(f"""(targetValue) => {{
                const normalize = (text) => text.trim().toLowerCase().replace(/\\s+/g, ' ');
                const normalizedTarget = normalize(targetValue);
                
                // Look for dropdown elements
                const containers = document.querySelectorAll('div[class*="menu"], ul[class*="menu"], div[class*="dropdown"], div[class*="list"]');
                
                for (const container of containers) {{
                    if (container.offsetParent === null) continue; // Skip hidden elements
                    
                    const options = container.querySelectorAll('li, div[role="option"], div[class*="option"], div[class*="item"]');
                    for (const option of options) {{
                        const text = normalize(option.textContent);
                        if (text === normalizedTarget || text.includes(normalizedTarget)) {{
                            // Found match - click it
                            option.scrollIntoView({{block: 'center'}});
                            option.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}""", value)
            
            if option_clicked:
                # Small variable delay after selection
                await frame.wait_for_timeout(200 + (hash(value) % 150))
                return True
            
            # If no match found via JS, try keyboard navigation which appears more human
            # Only press Enter if we didn't already select something with JS
            await frame.press(selector, "Enter")
            await frame.wait_for_timeout(200 + (hash(selector) % 150))
            
            return True
            
        except Exception as e:
            self.logger.debug(f"Simple dropdown approach failed: {str(e)}")
            return False
        
    async def _try_advanced_dropdown(self, frame, selector: str, value: str) -> bool:
        """Use advanced techniques to select from complex custom dropdowns with human-like behavior.
        
        Args:
            frame: The frame to interact with
            selector: CSS selector for the element
            value: Value to select
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # 1. Use more human-like interaction sequences
            
            # First try a gentle click (more human-like than direct JS execution)
            try:
                # Use a variable click delay (50-100ms) for more human-like behavior
                delay_ms = 50 + (hash(selector) % 50)
                await frame.click(selector, delay=delay_ms)
            except Exception as click_error:
                self.logger.debug(f"Direct click failed, falling back to JS click: {str(click_error)}")
                # If direct click fails, fall back to JS click
                await frame.evaluate(f"""(selector) => {{
                    const element = document.querySelector(selector);
                    if (element) {{
                        element.click();
                        element.focus();
                    }}
                }}""", selector)
            
            # Variable wait after clicking (300-550ms)
            await frame.wait_for_timeout(300 + (hash(value) % 250))
            
            # 2. Try intelligent search approach first - type in part of the value
            # This mimics how humans search in dropdowns
            if len(value) > 3:
                # For longer values, type just enough characters to likely get matches
                # First word, up to 4 chars
                search_term = value.split()[0][:4] if " " in value else value[:4]
                
                try:
                    await frame.fill(selector, "")
                    await frame.wait_for_timeout(100 + (hash(search_term) % 100))
                    
                    # Type the search term with variable speed
                    for char in search_term:
                        await frame.type(selector, char, delay=30 + (hash(char) % 70))
                    
                    await frame.wait_for_timeout(300 + (hash(search_term) % 200))
                except Exception as typing_error:
                    self.logger.debug(f"Typing search term failed: {str(typing_error)}")
                    # If typing fails, move to the next strategy
                    pass
            
            # 3. Look for visible options that match
            safe_value = value.replace("'", "\\'").replace('"', '\\"')
            
            option_clicked = await frame.evaluate(f"""(targetValue) => {{
                /* Helper function to normalize text for comparison */
                const normalize = (text) => text.trim().toLowerCase().replace(/\\s+/g, ' ');
                const normalizedTarget = normalize(targetValue);
                
                /* Find visible dropdown menu/list elements */
                const containers = document.querySelectorAll('div[class*="menu"], ul[class*="menu"], div[class*="dropdown"], div[class*="list"]');
                
                /* First try exact matches on the options in visible containers */
                for (const container of containers) {{
                    if (container.offsetParent === null) continue; /* Skip invisible containers */
                    
                    const options = container.querySelectorAll('li, div[role="option"], div[class*="option"], div[class*="item"]');
                    
                    /* Exact match first */
                    for (const option of options) {{
                        if (normalize(option.textContent) === normalizedTarget) {{
                            option.scrollIntoView({{block: 'center'}});
                            /* Add a small random delay before clicking (looks more human) */
                            setTimeout(() => option.click(), Math.floor(Math.random() * 40) + 10);
                            return true;
                        }}
                    }}
                    
                    /* Then try partial matches */
                    for (const option of options) {{
                        const content = normalize(option.textContent);
                        if (content.includes(normalizedTarget) || normalizedTarget.includes(content)) {{
                            option.scrollIntoView({{block: 'center'}});
                            /* Add a small random delay before clicking (looks more human) */
                            setTimeout(() => option.click(), Math.floor(Math.random() * 40) + 10);
                            return true;
                        }}
                    }}
                    
                    /* If no matches, don't automatically select first item - let user decide */
                    /* This prevents erroneous selections that might be caught by bot detection */
                    return false;
                }}
                
                /* If no visible dropdown found, we can't select */
                return false;
            }}""", safe_value)
            
            if option_clicked:
                # Variable wait after selection (250-450ms)
                await frame.wait_for_timeout(250 + (hash(value) % 200))
                return True
                
            # 4. Try keyboard navigation as last resort, which looks natural
            self.logger.debug(f"Option not found via clicking, trying keyboard navigation for '{value}'")
            # Clear and retry with different approach
            await frame.fill(selector, "")
            await frame.wait_for_timeout(150)
            
            # Type the first few characters then use arrow keys (very human-like pattern)
            if len(value) > 2:
                await frame.type(selector, value[:3], delay=60 + (hash(value) % 40))
                await frame.wait_for_timeout(300)
                
                # Press down arrow 1-3 times with varying delays
                arrow_presses = 1 + (hash(value) % 3)
                for i in range(arrow_presses):
                    await frame.keyboard.press("ArrowDown", delay=40 + (hash(f"{value}{i}") % 80))
                    await frame.wait_for_timeout(50 + (hash(f"{value}{i}") % 100))
            else:
                await frame.type(selector, value, delay=70)
                await frame.wait_for_timeout(250)
                await frame.keyboard.press("ArrowDown", delay=60)
                await frame.wait_for_timeout(100)
            
            # Finally press Enter
            await frame.keyboard.press("Enter", delay=50 + (hash(value) % 70))
            await frame.wait_for_timeout(250 + (hash(value) % 150))
            
            return True
            
        except Exception as e:
            self.logger.debug(f"Advanced dropdown approach failed: {str(e)}")
            return False
    
    async def _get_dropdown_options(self, frame, selector: str) -> List[str]:
        """Get available dropdown options using a gentle approach.
        
        Args:
            frame: The frame to examine
            selector: CSS selector for the element
            
        Returns:
            List of dropdown option texts
        """
        result_options = []
        
        try:
            # First try standard select elements without interaction
            try:
                options = await frame.evaluate(f"""(selector) => {{
                    const element = document.querySelector(selector);
                    
                    /* Check if it's a standard select */
                    if (element && element.tagName === 'SELECT') {{
                        return Array.from(element.options).map(opt => opt.text);
                    }}
                    
                    return [];
                }}""", selector)
                
                if options and len(options) > 0:
                    self.logger.debug(f"Found {len(options)} options from standard select element")
                    return options
            except Exception as e:
                self.logger.debug(f"Error getting options from standard select: {str(e)}")
                # Continue to next method
                
            # If not a standard select, try briefly opening the dropdown
            try:
                # Click to open
                await frame.click(selector)
                await frame.wait_for_timeout(300)
                
                # Get options from any visible dropdown containers
                options = await frame.evaluate("""() => {
                    /* Look for visible dropdown containers */
                    const containers = document.querySelectorAll(
                        'div[class*="menu"], ul[class*="menu"], div[class*="dropdown"], div[class*="list"]'
                    );
                    
                    for (const container of containers) {
                        if (container.offsetParent === null) continue; /* Skip if not visible */
                        
                        /* Get options from the container */
                        const options = container.querySelectorAll(
                            'li, div[role="option"], div[class*="option"], div[class*="item"]'
                        );
                        
                        if (options.length > 0) {
                            return Array.from(options).map(el => el.textContent.trim());
                        }
                    }
                    
                    return [];
                }""")
                
                if options and len(options) > 0:
                    self.logger.debug(f"Found {len(options)} options from custom dropdown")
                    result_options = options
            except Exception as error:
                self.logger.debug(f"Error getting options from custom dropdown: {str(error)}")
            finally:
                # Always clean up by clicking away, even if we got options
                try:
                    await self._cleanup_dropdown_state(frame)
                except Exception as cleanup_error:
                    self.logger.debug(f"Error cleaning up dropdown after option retrieval: {str(cleanup_error)}")
        except Exception as error:
            self.logger.debug(f"Error getting dropdown options: {str(error)}")
        finally:    
            # Always ensure cleanup as a last resort
            try:
                await self._cleanup_dropdown_state(frame)
            except Exception:
                pass
                
        return result_options
    
    def _find_best_match(self, value: str, options: List[str]) -> Optional[str]:
        """Find the best matching option for a given value.
        
        Uses a simple, robust matching approach.
        
        Args:
            value: The value to match
            options: List of available options
            
        Returns:
            Best matching option or None if no good match found
        """
        if not value or not options:
            return None
            
        value_lower = value.lower()
        
        # Exact match (case insensitive)
        for option in options:
            if option.lower() == value_lower:
                return option
                
        # Option contains value or value contains option
        for option in options:
            option_lower = option.lower()
            if value_lower in option_lower or option_lower in value_lower:
                return option
                
        # Fuzzy match as last resort
        matches = difflib.get_close_matches(value_lower, [opt.lower() for opt in options], n=1, cutoff=0.6)
        if matches:
            match_lower = matches[0]
            for option in options:
                if option.lower() == match_lower:
                    return option
        
        # No good match found - if we have options, return the first one
        if options:
            return options[0]
            
        return None

    async def _execute_click_action(
        self, 
        selector: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Execute a click action."""
        try:
            if self.test_mode:
                self.logger.info(f"TEST MODE: Simulating click on {selector}")
                return True
            
            # Get the page from browser_manager
            page = self.browser_manager.get_page()
            
            # Get appropriate frame
            frame = await self._get_frame(frame_id)
            
            # Sanitize the selector if it's numeric
            safe_selector = self._sanitize_selector(selector)
            
            # Click the element
            await frame.click(safe_selector)
            
            return True
        except Exception as e:
            self.logger.error(f"Error clicking {selector}: {str(e)}")
            return False
            
    async def _execute_file_action(
        self, 
        selector: str, 
        file_path: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Execute a file upload action."""
        try:
            if self.test_mode:
                self.logger.info(f"TEST MODE: Simulating file upload on {selector} with file {file_path}")
                return True
            
            # Get the page from browser_manager
            page = self.browser_manager.get_page()
            
            # Get appropriate frame
            frame = await self._get_frame(frame_id)
            
            # Sanitize the selector if it's numeric
            safe_selector = self._sanitize_selector(selector)
            
            # Verify file exists
            if not os.path.exists(file_path):
                self.logger.error(f"File not found: {file_path}")
                return False
            
            # Upload the file
            await frame.set_input_files(safe_selector, file_path)
            
            return True
        except Exception as e:
            self.logger.error(f"Error uploading file to {selector}: {str(e)}")
            return False
    
    async def _get_frame(self, frame_id: Optional[str] = None):
        """Get the appropriate frame for interaction.
        
        Args:
            frame_id: Optional frame ID to target
            
        Returns:
            The frame to use
        """
        page = self.browser_manager.get_page()
        if frame_id:
            frame = page.frame(frame_id)
            if not frame:
                raise ValueError(f"Frame {frame_id} not found")
            return frame
        return page
        
    async def _try_standard_select(self, frame, selector: str, value: str) -> bool:
        """Try to select using standard HTML select element approach.
        
        Args:
            frame: The frame to interact with
            selector: CSS selector for the element
            value: Value to select
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Try to select by value, label, or index
            await frame.select_option(selector, value=value)
            return True
        except Exception:
            try:
                await frame.select_option(selector, label=value)
                return True
            except Exception:
                # If both failed, return False
                return False
    
    async def _set_checkbox(self, selector: str, checked: bool, frame_id: Optional[str] = None) -> bool:
        """Set a checkbox.
        
        Args:
            selector: Element selector
            checked: Whether to check or uncheck
            frame_id: Frame ID
            
        Returns:
            Success flag
        """
        if self.test_mode:
            return True
        
        try:
            # Production code would use the browser_manager to locate and check/uncheck the checkbox
            page = self.browser_manager.get_page()
            frame = page if frame_id is None else page.frame(frame_id)
            
            # Sanitize the selector if it's numeric
            safe_selector = self._sanitize_selector(selector)
            
            if checked:
                await frame.check(safe_selector)
            else:
                await frame.uncheck(safe_selector)
            return True
        except Exception as e:
            self.logger.error(f"Error setting checkbox {selector}: {str(e)}")
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

    async def execute_form_actions(
        self,
        actions: List[ActionContext],
        stop_on_error: bool = True
    ) -> Dict[str, Tuple[bool, Optional[str]]]:
        """Execute a list of form actions with retries and error handling.
        
        Args:
            actions: List of actions to execute
            stop_on_error: Whether to stop on first error
            
        Returns:
            Dictionary mapping field IDs to (success, error_message) tuples
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage("execute_form_actions")
            
        results = {}
        
        for action in actions:
            if self.diagnostics_manager:
                self.diagnostics_manager.start_stage(f"action_{action.field_id}")
                
            success = False
            error_msg = None
            
            for attempt in range(self.max_retries):
                try:
                    # Switch to correct frame if needed
                    if action.frame_id:
                        frame = await self.browser_manager.get_frame(action.frame_id)
                        if not frame:
                            raise ValueError(f"Frame not found: {action.frame_id}")
                    
                    # Get selector for the field
                    selector = f"#{action.field_id}"  # Default selector
                    
                    # Execute action based on field type
                    if action.field_type == "select":
                        success = await self.form_interaction.select_option(
                            selector,
                            action.field_value,
                            action.options.get("dropdown_options") if action.options else None
                        )
                    elif action.field_type == "checkbox":
                        success = await self.form_interaction.set_checkbox(
                            selector,
                            bool(action.field_value)
                        )
                    elif action.field_type == "file":
                        success = await self.form_interaction.upload_file(
                            selector,
                            str(action.field_value)
                        )
                    else:  # Default to fill
                        success = await self.form_interaction.fill_field(
                            selector,
                            str(action.field_value)
                        )
                        
                    if success:
                        break
                    else:
                        error_msg = "Action failed without exception"
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                    
                except Exception as e:
                    error_msg = str(e)
                    self.logger.warning(
                        f"Action failed for field {action.field_id} "
                        f"(attempt {attempt + 1}/{self.max_retries}): {error_msg}"
                    )
                    
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                    
            results[action.field_id] = (success, error_msg)
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(
                    success,
                    error=error_msg if not success else None
                )
                
            if not success and stop_on_error:
                break
                
        if self.diagnostics_manager:
            self.diagnostics_manager.end_stage(
                all(success for success, _ in results.values()),
                details={"results": results}
            )
            
        return results 