"""Tools for interacting with form elements."""

import re
import logging
import asyncio
from typing import Dict, Any, Optional, List, Union, Tuple
from enum import Enum, auto
import time
import difflib
import json
import traceback
from thefuzz import fuzz # Ensure this import is present

from enterprise_job_agent.core.browser_interface import BrowserInterface
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.tools.element_selector import ElementSelector
from enterprise_job_agent.core.exceptions import ActionExecutionError

# Import verification helper functions
from .verification_helper import verify_selection, verify_input_value

logger = logging.getLogger(__name__)

# --- Constants --- #
DEFAULT_TIMEOUT = 10000  # ms (10 seconds)
SHORT_TIMEOUT = 3000   # ms (3 seconds)
VISIBILITY_TIMEOUT = 5000 # ms (5 seconds)
INTERACTION_DELAY = 0.5  # seconds
POST_TYPE_DELAY = 0.75   # seconds
POST_CLICK_DELAY = 0.5   # seconds
RETRY_DELAY_BASE = 0.5   # seconds

# Similarity Thresholds (0.0 to 1.0)
DEFAULT_FUZZY_THRESHOLD = 0.75
HIGH_FUZZY_THRESHOLD = 0.80
VERIFICATION_THRESHOLD = 0.70
LOW_VERIFICATION_THRESHOLD = 0.60 # For less certain cases like keyboard nav fallback
# --- End Constants --- #

class InteractionType(Enum):
    """Types of form interactions."""
    FILL = auto()
    SELECT = auto()
    CLICK = auto()
    UPLOAD = auto()
    CLEAR = auto()

class InteractionResult:
    """Result of a form interaction."""
    def __init__(
        self,
        success: bool,
        field_id: str,
        interaction_type: InteractionType,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.success = success
        self.field_id = field_id
        self.interaction_type = interaction_type
        self.error = error
        self.details = details or {}
        self.retry_count = 0

class FormInteraction:
    """Handles reliable form interactions with retries and error handling."""
    
    def __init__(
        self,
        browser_manager,
        element_selector,
        advanced_frame_manager=None,
        diagnostics_manager=None,
        config=None
    ):
        """Initialize the FormInteraction class.
        
        Args:
            browser_manager: Browser manager instance
            element_selector: Element selector instance
            advanced_frame_manager: Advanced frame manager instance (optional)
            diagnostics_manager: Diagnostics manager (optional)
            config: Configuration dictionary (optional)
        """
        self.browser = browser_manager
        self.element_selector = element_selector
        self.advanced_frame_manager = advanced_frame_manager
        self.diagnostics_manager = diagnostics_manager
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # Set default retry configuration
        self.max_retries = self.config.get('max_retries', 3)
        self.retry_delay = self.config.get('retry_delay', RETRY_DELAY_BASE)
    
    def _log_debug(self, message):
        """Log a debug message using the diagnostics manager if available, otherwise pass."""
        if self.diagnostics_manager:
            if hasattr(self.diagnostics_manager, 'debug'):
                self.diagnostics_manager.debug(message)
            
    def _log_info(self, message):
        """Log an info message using the diagnostics manager if available, otherwise pass."""
        if self.diagnostics_manager:
            if hasattr(self.diagnostics_manager, 'info'):
                self.diagnostics_manager.info(message)
            
    def _log_error(self, message):
        """Log an error message using the diagnostics manager if available, otherwise pass."""
        if self.diagnostics_manager:
            if hasattr(self.diagnostics_manager, 'error'):
                self.diagnostics_manager.error(message)
            elif hasattr(self.diagnostics_manager, 'warning'):
                self.diagnostics_manager.warning(message)
    
    async def _wait_for_element(
        self,
        selector: str,
        frame_id: Optional[str] = None,
        timeout: int = VISIBILITY_TIMEOUT
    ) -> bool:
        """Wait for an element to be ready for interaction."""
        try:
            frame = await self.browser.get_frame(frame_id) if frame_id else None
            element = await self.element_selector.wait_for_element(selector, frame=frame)
            return element is not None
        except Exception as e:
            self.logger.debug(f"Element not ready: {selector} - {str(e)}")
            return False
    
    async def _retry_interaction(
        self,
        interaction_fn,
        field_id: str,
        interaction_type: InteractionType,
        **kwargs
    ) -> InteractionResult:
        """Retry an interaction with exponential backoff."""
        result = InteractionResult(False, field_id, interaction_type)
        
        for attempt in range(self.max_retries):
            try:
                success = await interaction_fn(**kwargs)
                if success:
                    result.success = True
                    break
                    
            except Exception as e:
                result.error = str(e)
                self.logger.debug(f"Interaction attempt {attempt + 1} failed: {str(e)}")
            
            # Update retry count
            result.retry_count = attempt + 1
            
            # Wait before retry
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return result
    
    def _escape_css_string(self, value: str) -> str:
        """Escape characters in a string that are special in CSS selectors, like quotes."""
        # Primarily escape double quotes for now, as they break :has-text("...")
        return value.replace('"', '\\"')
    
    async def fill_field(self, selector: str, value: str, frame_id: Optional[str] = None):
        """Fill a field with a value.
        
        Args:
            selector: CSS selector
            value: Value to fill
            frame_id: Optional frame ID
            
        Raises:
            Exception: If fill fails
        """
        try:
            element = await self.element_selector.find_element(selector, frame_id)
            if element:
                # Clear the field first
                try:
                    await element.fill("")
                except Exception as e:
                    self.logger.debug(f"Failed to clear field '{selector}': {e}")
                    
                # Fill with value
                await element.type(value)
                if self.diagnostics_manager:
                    self.diagnostics_manager.debug(f"Filled field {selector} with value: {value}")
                return True
            else:
                # Try using direct frame fill if element selector failed
                frame = await self.browser.get_frame(frame_id)
                if frame:
                    try:
                        await frame.fill(selector, value)
                        if self.diagnostics_manager:
                            self.diagnostics_manager.debug(f"Filled field {selector} in frame {frame_id} with direct frame.fill: {value}")
                        return True
                    except Exception as e:
                        if self.diagnostics_manager:
                            self.diagnostics_manager.error(f"Failed to fill field in frame {frame_id}: {selector} - {str(e)}")
                else:
                    # Raise specific error
                    raise ActionExecutionError(f"Failed to find field '{selector}' for filling")
        except ActionExecutionError: # Re-raise specific known errors
             raise
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.error(f"Error filling field {selector}: {str(e)}")
            # Wrap unexpected errors
            raise ActionExecutionError(f"Unexpected error filling field {selector}: {e}") from e
    
    async def select_option(self, selector: str, value: Optional[str] = None, label: Optional[str] = None, frame_id: Optional[str] = None) -> bool:
        """Select an option from a dropdown with enhanced handling for different dropdown types.
        
        Args:
            selector: CSS selector
            value: Value attribute of the option to select.
            label: Visible text/label of the option to select.
            frame_id: Optional frame ID
            
        Returns:
            True if selection succeeded, False otherwise
        """
        if value is None and label is None:
            self.logger.error("select_option requires either 'value' or 'label' to be provided.")
            return False
            
        # Determine the primary target text for custom interactions and logging
        target_text = label if label is not None else value
        log_value = f"label='{label}'" if label is not None else f"value='{value}'"
        log_target = f"'{selector}' with {log_value}"
        self.logger.debug(f"Attempting select_option for {log_target}")

        try:
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            if not frame:
                if self.diagnostics_manager:
                    self.diagnostics_manager.error(f"Failed to get frame for select_option: {frame_id}")
                return False
            
            # 1. First, try standard select methods using Playwright's select_option
            # Try by label first if provided, as it often corresponds to user intent
            if label is not None:
                 try:
                     self.logger.debug(f"Trying standard select by label: {label}")
                     await frame.select_option(selector, label=label, timeout=SHORT_TIMEOUT) # Add timeout
                     if self.diagnostics_manager:
                         self.diagnostics_manager.debug(f"Selected option by label for '{selector}': {label}")
                     # Verify selection based on the label we tried to select
                     if await verify_selection(frame, selector, label):
                         return True
                 except Exception as e:
                     if self.diagnostics_manager:
                         self.diagnostics_manager.debug(f"Failed standard select by label for '{selector}': {e}")
            
            # Try by value if provided (or if label failed)
            if value is not None:
                 try:
                     self.logger.debug(f"Trying standard select by value: {value}")
                     await frame.select_option(selector, value=value, timeout=SHORT_TIMEOUT) # Add timeout
                     if self.diagnostics_manager:
                         self.diagnostics_manager.debug(f"Selected option by value for '{selector}': {value}")
                     # Verify selection based on the value we tried to select
                     if await verify_selection(frame, selector, value):
                         return True
                 except Exception as e:
                     if self.diagnostics_manager:
                         self.diagnostics_manager.debug(f"Failed standard select by value for '{selector}': {e}")
            
            # 2. Try custom dropdown handling if standard methods failed
            self.logger.debug(f"Standard select methods failed for {log_target}. Trying custom interaction using target text: '{target_text}'")
            
            # Get the element using the selector string, not the frame
            # --- FIX: Extract frame_id string from frame object --- 
            frame_id = frame.url # Use URL as the frame identifier for element_selector
            element = await self.element_selector.find_element(selector, frame_id=frame_id) # Pass frame_id for context
            if not element:
                if self.diagnostics_manager:
                    self.diagnostics_manager.error(f"Custom select: Failed to find element '{selector}' in frame {frame_id}")
            if not element:
                if self.diagnostics_manager:
                    self.diagnostics_manager.error(f"Custom select: Failed to find element '{selector}'")
                return False
            
            # Click to open the dropdown
            try:
                await element.click(timeout=3000)
                if self.diagnostics_manager:
                    self.diagnostics_manager.debug(f"Custom select: Clicked element to open dropdown: {selector}")
                await asyncio.sleep(0.5)  # Wait for dropdown to open
            except Exception as click_err:
                 self.logger.warning(f"Custom select: Failed to click element {selector} to open dropdown: {click_err}")
                 # Proceed to try typing anyway, maybe click wasn't needed
                 pass
            
            # Try to find and click options that match the target_text
            # Pass the frame object here, as _try_click_option works within that frame
            option_clicked = await self._try_click_option(frame, target_text) 
            if option_clicked:
                if self.diagnostics_manager:
                    self.diagnostics_manager.debug(f"Custom select: Clicked option matching '{target_text}'")
                # Verify selection using the target_text
                if await verify_selection(frame, selector, target_text):
                    return True
            
            # If clicking failed, try typing the target_text and pressing Enter
            self.logger.debug(f"Custom select: Clicking option failed. Trying to type '{target_text}' and press Enter.")
            try:
                await element.fill("")  # Clear any existing text
                await element.type(target_text, delay=50) # Add slight delay
                if self.diagnostics_manager:
                    self.diagnostics_manager.debug(f"Custom select: Typed '{target_text}' into element: {selector}")
                await asyncio.sleep(0.7)  # Give time for suggestions/filtering
                
                # Try pressing Enter
                await element.press("Enter")
                if self.diagnostics_manager:
                    self.diagnostics_manager.debug(f"Custom select: Pressed Enter in {selector}")
                await asyncio.sleep(0.5)  # Wait for selection to apply
                
                # Final verification using target_text
                if await verify_selection(frame, selector, target_text):
                    return True
            except Exception as type_err:
                 self.logger.warning(f"Custom select: Error during type/enter sequence for {selector}: {type_err}")

            # If all strategies fail, log an error and return False
            if self.diagnostics_manager:
                self.diagnostics_manager.error(f"Failed to select option for {log_target} after trying all strategies")
            return False
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.error(f"Unexpected error in select_option for {log_target}: {e}", exc_info=True)
            return False
    
    async def _try_click_option(self, frame, value: str) -> bool:
        """Try to click an option in an open dropdown based on its text.
        
        Args:
            frame: The frame containing the dropdown
            value: The value to select from the dropdown
        
        Returns:
            True if an option was clicked, False otherwise
        """
        try:
            # Create variations of the value to increase chances of finding a match
            value_variations = [
                value,
                value.strip(),
                value.lower(),
                value.upper(),
                value.title(),
                re.sub(r'[^\w\s]', '', value),  # Remove special characters
            ]
            
            # Generate additional variations for specific value types
            if ', ' in value:  # Location format like "City, State"
                parts = value.split(', ')
                if len(parts) >= 2:
                    value_variations.append(parts[0])  # Just the city
                    value_variations.append(parts[0] + ', ' + parts[1])  # City, State
            
            # Remove duplicates
            value_variations = list(set(value_variations))
            
            # Try each selector with each value variation
            for v in value_variations:
                # Combine exact and general selectors for this variation
                selectors_to_check = [
                    f"div[role='option']:has-text('{v}')",
                    f"li:has-text('{v}')",
                    f"option:has-text('{v}')",
                    f"[role='option']:has-text('{v}')",
                    f".dropdown-item:has-text('{v}')",
                    f".select-option:has-text('{v}')",
                    f".autocomplete-result:has-text('{v}')",
                    f"text='{v}'",
                    f"div[role='option']:text-is('{v}')",
                    f"li:text-is('{v}')",
                    f"option:text-is('{v}')",
                    f"[role='option']:text-is('{v}')"
                ]
                selector_to_try = "" # Initialize selector_to_try
                for selector_template in selectors_to_check:
                    try:
                        selector_to_try = selector_template # Assign before potential exception
                        option = await frame.query_selector(selector_to_try)

                        if option:
                            is_visible = await option.is_visible()
                            if is_visible:
                                await option.click()
                                if self.diagnostics_manager:
                                    self.diagnostics_manager.debug(f"Clicked dropdown option with selector: {selector_to_try}")
                                return True
                    except Exception as e:
                        if self.diagnostics_manager:
                            # Ensure selector_to_try has a value even if query_selector fails
                            log_selector = selector_to_try if selector_to_try else selector_template
                            self.diagnostics_manager.debug(f"Error trying selector {log_selector} with value '{v}': {str(e)}")
                        continue

            # If specific selectors failed, try a more general approach with contains()
            for v in value_variations:
                try:
                    # Use XPath for more flexibility with contains()
                    xpath_selector = f"//div[contains(text(), '{v}')][@role='option'] | //li[contains(text(), '{v}')] | //option[contains(text(), '{v}')]"
                    option = await frame.query_selector(f"xpath={xpath_selector}")
                    if option and await option.is_visible():
                        await option.click()
                        if self.diagnostics_manager:
                            self.diagnostics_manager.debug(f"Clicked dropdown option using XPath contains for '{v}'")
                        return True
                except Exception as e:
                    if self.diagnostics_manager:
                        self.diagnostics_manager.debug(f"XPath contains approach failed for '{v}': {str(e)}")
            
            # Fuzzy matching approach for options that don't match exactly
            try:
                # Get all visible options
                option_selectors = [
                    "div[role='option']", 
                    "li[role='option']", 
                    "option", 
                    "[role='option']", 
                    ".dropdown-item", 
                    ".select-option",
                    ".autocomplete-result"
                ]
                
                best_match = None
                best_score = 0
                
                for opt_selector in option_selectors:
                    options = await frame.query_selector_all(opt_selector)
                    
                    for option in options:
                        if not await option.is_visible():
                            continue
                            
                        option_text = await option.text_content()
                        if not option_text:
                            continue
                        
                        # Calculate similarity score
                        similarity = difflib.SequenceMatcher(None, value.lower(), option_text.lower()).ratio()
                        
                        if similarity > 0.6 and similarity > best_score:
                            best_match = option
                            best_score = similarity
                
                if best_match:
                    await best_match.click()
                    if self.diagnostics_manager:
                        self.diagnostics_manager.debug(f"Clicked best match option with similarity {best_score:.2f}")
                    return True
                    
            except Exception as e:
                if self.diagnostics_manager:
                    self.diagnostics_manager.debug(f"Fuzzy matching approach failed: {str(e)}")
                
            if self.diagnostics_manager:
                self.diagnostics_manager.debug(f"Could not find a matching dropdown option for '{value}'")
            return False
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.debug(f"Error in _try_click_option: {str(e)}")
            return False
    
    async def _verify_selection(self, frame, selector: str, expected_value: str, threshold: float = VERIFICATION_THRESHOLD) -> bool:
        """Verify that a dropdown selection was successful."""
        # --- Start Existing _verify_selection ---
        try:
            # --- Simplification: Try input value verification first ---
            if await verify_input_value(frame, selector, expected_value, threshold):
                return True
            
            # --- Keep the rest for complex cases if input value fails ---
            # 1. Try to get the displayed text of the element (Already tried via _verify_input_value essentially)
            element = await frame.query_selector(selector)
            if not element:
                # If element query fails here after input value check, likely not verifiable
                return False 
                
            # Get the displayed text content (might differ from input value)
            displayed_text = await element.text_content()
            if displayed_text and (
                expected_value.lower() in displayed_text.lower() or 
                displayed_text.lower() in expected_value.lower() or
                difflib.SequenceMatcher(None, expected_value.lower(), displayed_text.lower()).ratio() > threshold
            ):
                if self.diagnostics_manager:
                    self.diagnostics_manager.debug(f"Verified dropdown selection: displayed text '{displayed_text}' matches '{expected_value}' (threshold: {threshold})")
                return True
                
            # 2. Try to check for selected option using JavaScript 
            # ... (keep existing JS logic) ...
            try:
                selected_value = await frame.eval_on_selector(
                    selector,
                    """(el) => {
                        // For standard select elements
                        if (el.tagName === 'SELECT') {
                            return Array.from(el.options)
                                .filter(option => option.selected)
                                .map(option => option.text || option.value)[0];
                        }
                        // ... other JS checks ...
                        const dataValue = el.getAttribute('data-value');
                        if (dataValue) {
                            return dataValue;
                        }
                        return null;
                    }"""
                )
                
                if selected_value and (
                    expected_value.lower() in selected_value.lower() or 
                    selected_value.lower() in expected_value.lower() or
                    difflib.SequenceMatcher(None, expected_value.lower(), selected_value.lower()).ratio() > threshold
                ):
                    if self.diagnostics_manager:
                        self.diagnostics_manager.debug(f"Verified dropdown selection via JS: '{selected_value}' matches '{expected_value}' (threshold: {threshold})")
                    return True
            except Exception as e:
                if self.diagnostics_manager:
                    self.diagnostics_manager.debug(f"JS verification failed: {str(e)}")

            # 3. Check if any visible element within the dropdown area contains the expected text
            # ... (keep existing logic) ...
            try:
                # Use a more specific selector if possible, e.g., targeting options within the element
                visible_element = await frame.query_selector(f"{selector} :is([role='option'], .select__option):has-text('{expected_value}')")
                if visible_element and await visible_element.is_visible(timeout=500): # Quick visibility check
                    if self.diagnostics_manager:
                         self.diagnostics_manager.debug(f"Found visible text '{expected_value}' in the dropdown area")
                    return True
            except Exception as e:
                 if self.diagnostics_manager:
                     self.diagnostics_manager.debug(f"Visible text verification failed: {str(e)}")

            # 4. Check parent or adjacent elements (Keep as lower priority)
            # ... (keep existing logic) ...

            # 5. Final fallback - check if any element on the page now displays the expected value (Keep as lowest priority)
            # ... (keep existing logic) ...
            
            # If none of the verification methods found a match, log and return false
            if self.diagnostics_manager:
                # Get current input value again for final log message if verification failed
                final_value_for_log = await self._get_element_value_for_verification(frame, selector)
                self.diagnostics_manager.debug(f"Selection verification failed for '{selector}': Expected '{expected_value}', final value: '{final_value_for_log}'")
            return False
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.debug(f"Error in _verify_selection: {str(e)}")
            return False
            
    # --- NEW HELPER: Verify Input Value ---
    async def _verify_input_value(self, frame_or_page, selector: str, expected_value: str, threshold: float = VERIFICATION_THRESHOLD) -> bool:
        """Verify the input value of an element against an expected value using fuzzy matching."""
        try:
            current_value = await self._get_element_value_for_verification(frame_or_page, selector)
            if current_value is None: # Check explicitly for None if getter fails
                 self.logger.debug(f"VerifyInputValue: Could not retrieve value for {selector}.")
                 return False

            # Use thefuzz for potentially better fuzzy matching
            try:
                 similarity = fuzz.ratio(expected_value.lower(), current_value.lower()) / 100.0
            except NameError:
                 self.logger.warning("VerifyInputValue: 'fuzz' not defined, falling back to difflib.")
                 similarity = difflib.SequenceMatcher(None, expected_value.lower(), current_value.lower()).ratio()

            self.logger.debug(f"VerifyInputValue: Comparing '{expected_value.lower()}' vs '{current_value.lower()}' -> Similarity: {similarity:.3f}")

            if similarity >= threshold:
                self.logger.info(f"VerifyInputValue: Selection for {selector} matches '{expected_value}' (Similarity: {similarity:.3f}, Threshold: {threshold})")
                return True
            else:
                # Log failure reason clearly
                self.logger.debug(f"VerifyInputValue: Match failed for {selector}. Expected='{expected_value}', Got='{current_value}', Score={similarity:.3f}, Threshold={threshold}")
                return False
        except Exception as e:
            self.logger.error(f"VerifyInputValue: Error during verification for {selector}: {str(e)}")
            return False

    # --- NEW HELPER: Get Element Value ---
    async def _get_element_value_for_verification(self, frame_or_page, selector: str) -> Optional[str]:
         """Attempts to get the most relevant value (input value or text content) for verification."""
         try:
             element = await frame_or_page.query_selector(selector)
             if not element:
                 return None
             # Prioritize input_value as it reflects the actual selected value for inputs/selects
             value = await element.input_value()
             if value is not None: # Check for None explicitly, empty string is valid
                  return value
             # Fallback to text_content if input_value is None (e.g., for divs displaying selection)
             text = await element.text_content()
             return text.strip() if text else None # Return None if text is also empty/None
         except Exception as e:
              self.logger.debug(f"_get_element_value: Error getting value for {selector}: {e}")
              return None

    # --- NEW HELPER: Find and Click Option ---
    async def _find_and_click_option(
        self,
        frame,
        target_text: str,
        option_selectors: List[str] = None,
        exact_match: bool = False
    ) -> bool:
        """
        Finds and clicks the first visible option matching the target text.

        Args:
            frame: The Playwright frame or page object to search within.
            target_text: The text content to match in the option.
            option_selectors: A list of CSS selectors to try for finding options.
                              Defaults to common option selectors if None.
            exact_match: If True, requires an exact text match (case-insensitive).
                         If False, uses fuzzy matching (ratio > 0.8).

        Returns:
            True if an option was found and clicked, False otherwise.
        """
        if not option_selectors:
            option_selectors = [
                 ":is([role='option'], .select__option, .dropdown-item, li, .autocomplete-suggestion)" # Common selectors
            ]

        target_lower = target_text.lower().strip()
        best_match_element = None
        best_score = 0.0
        found_exact = False

        for selector_group in option_selectors:
             try:
                  options_locator = frame.locator(selector_group)
                  count = await options_locator.count()
                  # Limit checks for performance
                  for i in range(min(count, 50)):
                       option = options_locator.nth(i)
                       try:
                            if not await option.is_visible(timeout=200): continue # Skip non-visible quickly

                            option_text_content = await option.text_content()
                            if not option_text_content: continue

                            option_text_lower = option_text_content.strip().lower()
                            if not option_text_lower: continue

                            if exact_match:
                                 if option_text_lower == target_lower:
                                      best_match_element = option
                                      found_exact = True
                                      self.logger.debug(f"_find_and_click: Found exact match: '{option_text_content}' using selector group: {selector_group}")
                                      break # Found exact match, stop inner loop
                            else:
                                 # Use fuzzy matching
                                 try:
                                      score = fuzz.ratio(target_lower, option_text_lower) / 100.0
                                 except NameError:
                                      score = difflib.SequenceMatcher(None, target_lower, option_text_lower).ratio()

                                 # Use a relatively high threshold for fuzzy selection
                                 if score > HIGH_FUZZY_THRESHOLD and score > best_score:
                                      best_score = score
                                      best_match_element = option
                                      self.logger.debug(f"_find_and_click: Found new best fuzzy match: '{option_text_content}' (Score: {score:.2f}) using selector group: {selector_group}")
                                      # Optimization: if score is near perfect, consider it good enough
                                      if score > 0.98: break

                       except Exception as inner_e:
                            self.logger.debug(f"_find_and_click: Error processing option {i} with '{selector_group}': {inner_e}")
                            continue # Ignore errors on individual options

                  if found_exact or (not exact_match and best_score > 0.8):
                       break # Exit outer loop if a good match was found

             except Exception as outer_e:
                  self.logger.debug(f"_find_and_click: Error with selector group '{selector_group}': {outer_e}")
                  continue # Try next selector group

        # Click the best match found
        if best_match_element:
            try:
                option_text_final = await best_match_element.text_content() # Get text again for logging
                self.logger.info(f"_find_and_click: Attempting to click best match: '{option_text_final}' (Exact: {found_exact}, Score: {best_score:.2f})")
                await best_match_element.click(timeout=VISIBILITY_TIMEOUT)
                self.logger.info(f"_find_and_click: Successfully clicked option '{option_text_final}'.")
                # --- ADD DISMISSAL --- #
                await self._try_dismiss_dropdown(best_match_element, frame)
                # --- END DISMISSAL --- #
                return True
            except Exception as click_e:
                self.logger.warning(f"_find_and_click: Failed to click best match option '{await best_match_element.text_content()}': {click_e}")
                # Attempt dismissal even on failure?
                await self._try_dismiss_dropdown(best_match_element, frame) # Try dismiss even if click fails
                return False
        else:
            self.logger.debug(f"_find_and_click: No suitable option found matching '{target_text}' (Exact: {exact_match}).")
            return False


    async def get_field_value(self, selector: str, frame_id: Optional[str] = None) -> str:
        """Get the value of a field."""
        # --- Simplified: Use the new helper ---
        frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
        value = await self._get_element_value_for_verification(frame, selector)
        return value if value is not None else ""
        # --- End Simplification ---

    async def set_checkbox(
        self,
        selector: str,
        checked: bool,
        frame_id: Optional[str] = None
    ) -> bool:
        """Set a checkbox to checked or unchecked.
        
        Args:
            selector: CSS selector for the checkbox
            checked: Whether the checkbox should be checked
            frame_id: Optional frame identifier
            
        Returns:
            True if successful, False otherwise
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage(f"set_checkbox_{selector}")
            
        try:
            # Get the frame if needed
            frame = await self.browser.get_frame(frame_id) if frame_id else None
            context = frame or self.browser.page
            
            # Find the checkbox
            element = await self.element_selector.wait_for_element(selector, frame=frame, timeout=VISIBILITY_TIMEOUT)
            if not element:
                raise ValueError(f"Element not found: {selector}")
                
            # Get current state
            is_checked = await element.is_checked()
            
            # Click if state needs to change
            if is_checked != checked:
                await element.click()
                
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(True)
            return True
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=str(e))
            logger.error(f"Error setting checkbox {selector}: {e}")
            return False
    
    async def upload_file(
        self,
        selector: str,
        file_path: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Upload a file to a file input.
        
        Args:
            selector: CSS selector for the file input
            file_path: Path to the file to upload
            frame_id: Optional frame identifier
            
        Returns:
            True if successful, False otherwise
        """
        if self.diagnostics_manager:
            self.diagnostics_manager.start_stage(f"upload_file_{selector}")
            
        try:
            # Get the frame if needed
            frame = await self.browser.get_frame(frame_id) if frame_id else None
            context = frame or self.browser.page
            
            # Find the file input
            element = await self.element_selector.wait_for_element(selector, frame=frame, timeout=VISIBILITY_TIMEOUT)
            if not element:
                raise ValueError(f"Element not found: {selector}")
                
            # Upload the file
            await element.set_input_files(file_path)
            
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(True)
            return True
            
        except Exception as e:
            if self.diagnostics_manager:
                self.diagnostics_manager.end_stage(False, error=str(e))
            logger.error(f"Error uploading file {file_path} to {selector}: {e}")
            return False

    async def click_element(self, selector: str, frame_id: Optional[str] = None):
        """Click on an element.
        
        Args:
            selector: CSS selector
            frame_id: Optional frame ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            element = await self.element_selector.find_element(selector, frame_id)
            if element:
                await element.click()
                self._log_debug(f"Clicked element: {selector}")
                return True
            
            if frame_id:
                frame = await self.browser.get_frame(frame_id)
                if frame:
                    try:
                        await frame.click(selector)
                        self._log_debug(f"Clicked element in frame {frame_id}: {selector}")
                        return True
                    except Exception as e:
                        self._log_error(f"Failed to click element in frame {frame_id}: {selector} - {str(e)}")
            
            # Try direct page click as last resort
            try:
                await self.browser.page.click(selector)
                self._log_debug(f"Clicked element with direct page click: {selector}")
                return True
            except Exception as e:
                self._log_error(f"Failed to click element with direct page click: {selector} - {str(e)}")
                
            self._log_error(f"Element not found for click: {selector}")
            return False
            
        except Exception as e:
            self._log_error(f"Error clicking element {selector}: {str(e)}")
            return False

    async def handle_typeahead(
        self,
        selector: str,
        value: str,
        field_type: Optional[str] = None,
        frame_id: Optional[str] = None
    ) -> bool:
        """Handle typeahead fields with standard approaches.
        
        Args:
            selector: CSS selector for the input field
            value: Value to enter/select
            field_type: Type of the field (e.g., 'school', 'degree')
            frame_id: Optional frame identifier
        
        Returns:
            True if successful, False otherwise
        """
        # Generate variants of the value for fallback attempts
        variants = [value]
        if field_type:
            # Add common variants based on field type
            if field_type == "school" and "university" in value.lower():
                variants.extend([
                    value.replace("University", "Univ"),
                    value.replace("University of", ""),
                    value.split(",")[0]  # First part before comma
                ])
            elif field_type == "degree":
                if "Bachelor" in value:
                    variants.extend(["BS", "B.S.", "Bachelor's"])
                elif "Master" in value:
                    variants.extend(["MS", "M.S.", "Master's"])
            
        self.logger.info(f"Handling standard typeahead for '{value}' in {selector}")
        
        try:
            # Get the frame if needed
            frame = await self.browser.get_frame(frame_id) if frame_id else None
            
            # First try direct input with tab
            element = await self.element_selector.wait_for_element(selector, frame=frame)
            if not element:
                self.logger.warning(f"Element not found: {selector}")
                return False
                
            # Try each variant
            for variant in variants:
                try:
                    await element.fill(variant)
                    await asyncio.sleep(0.5)
                    
                    # Check if dropdown visible and select first option
                    dropdown_visible = await self._check_dropdown_visible()
                    if dropdown_visible:
                        await self._select_first_dropdown_option()
                        return True
                    
                    # If no dropdown, just press tab to confirm
                    await element.press("Tab")
                    return True
                    
                except Exception as e:
                    self.logger.debug(f"Error with variant '{variant}': {str(e)}")
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Standard typeahead handling failed: {str(e)}")
            return False
    
    async def _check_dropdown_visible(self) -> bool:
        """Check if a dropdown is visible after interacting with a field."""
        page = self.browser.page
        if not page:
            return False
            
        try:
            # Common dropdown selectors
            dropdown_selectors = [
                'ul[role="listbox"]', 
                '.dropdown-menu', 
                '[role="listbox"]',
                '.select-dropdown',
                '.autocomplete-results'
            ]
            
            for selector in dropdown_selectors:
                dropdown = await page.query_selector(selector)
                if dropdown:
                    is_visible = await dropdown.is_visible()
                    if is_visible:
                        return True
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Error checking dropdown visibility: {str(e)}")
            return False
            
    async def _select_first_dropdown_option(self) -> bool:
        """Select the first option in a visible dropdown."""
        page = self.browser.page
        if not page:
            return False
            
        try:
            # Common option selectors
            option_selectors = [
                'li[role="option"]', 
                '.dropdown-item', 
                '[role="option"]',
                '.select-option',
                '.autocomplete-result'
            ]
            
            for selector in option_selectors:
                options = await page.query_selector_all(selector)
                for option in options:
                    is_visible = await option.is_visible()
                    if is_visible:
                        await option.click()
                        return True
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Error selecting dropdown option: {str(e)}")
            return False

    async def handle_typeahead_with_ai(
        self,
        selector: str,
        value: str,
        field_type: Optional[str] = None,
        frame_id: Optional[str] = None
    ) -> bool:
        """
        Advanced typeahead handling using a mix of AI techniques and JavaScript for direct access to dropdown options.
        """
        try:
            self.logger.info(f"Handling AI-assisted typeahead for '{value}' in {selector} (type: {field_type})")
            
            # Generate variations based on field type
            variants = self._generate_typeahead_variants(value, field_type)
            
            # Log a sample of variants for debugging
            num_variants = len(variants)
            self.logger.debug(f"{field_type.capitalize()} variants generated dynamically: {[v for v in variants[:5]]}...")
            
            # Ensure we have a page and frame
            page = self.browser.page
            
            # Get the frame if needed
            frame = await self.browser.get_frame(frame_id) if frame_id else None
            
            if frame:
                frame_obj = await self.browser.page.frame(frame)
                if frame_obj:
                    js_context = frame_obj
                else:
                    js_context = page
            else:
                js_context = page

            # Element exists, try to fill with AI assistance
            # Wait up to X times, with a delay between retries
            max_retries = getattr(self, 'max_retries', 5)  # Default to 5 if not defined
            retry_delay = getattr(self, 'retry_delay', 0.5)  # Default to 0.5 if not defined
            
            element = await self.element_selector.wait_for_element(selector, frame=frame)
            if not element:
                self.logger.warning(f"Element not found: {selector}")
                return False
                
            # Clear any existing value
            await element.click()
            await element.fill("")
            await asyncio.sleep(0.2)
            
            # For school fields, implement specialized typing strategy to ensure more accurate matching
            if field_type == "school":
                school_name = value.lower()
                
                # Get all dropdown options initially to see what's available
                await self._type_school_name_strategically(element, value)
                await asyncio.sleep(0.8)  # Wait for dropdown to fully populate
                
                # Get dropdown options using JavaScript
                dropdown_options = await js_context.evaluate("""
                    () => {
                        const optionSelectors = [
                            '[role="option"]', '.select__option', '.dropdown-item',
                            'li[id*="react-select"]', 'li.option', '[role="listbox"] > *',
                            '.select__menu .select__option', '[class*="select"] [class*="option"]',
                            '.autocomplete-item', '[role="listitem"]'
                        ];
                        
                        for (const selector of optionSelectors) {
                            const options = Array.from(document.querySelectorAll(selector));
                            if (options.length > 0) {
                                return options.map(opt => ({
                                    text: opt.textContent.trim(),
                                    label: opt.getAttribute('aria-label') || '',
                                    selected: opt.getAttribute('aria-selected') === 'true',
                                    value: opt.getAttribute('data-value') || '',
                                    element: selector
                                }));
                            }
                        }
                        return [];
                    }
                """)
                
                # Find the best match among the options
                if dropdown_options and len(dropdown_options) > 0:
                    self.logger.debug(f"Found {len(dropdown_options)} dropdown options")
                    
                    # JS script for matching the best option
                    js_script = """
                    (args) => {
                        const { selector, value, variants, options } = args;
                        
                        // Find the input element
                        const input = document.querySelector(selector);
                        if (!input) return { success: false, error: "Input not found" };
                        
                        // Normalize text for comparison
                        const normalize = (text) => {
                            return text.toLowerCase()
                                .replace(/[^\w\s]/g, ' ')
                                .replace(/\s+/g, ' ')
                                .trim();
                        };
                        
                        // Score function - generic pattern matching for all schools
                        const scoreMatch = (option, searchValue) => {
                            const optionText = normalize(option.text);
                            const searchText = normalize(searchValue);
                            
                            // Exact match
                            if (optionText === searchText) return 1.0;
                            
                            // Get main parts of school name for matching
                            const searchParts = searchText.split(/,|\s-\s/); // Split by comma or dash
                            const mainSearchPart = searchParts[0].trim();
                            
                            // Pattern detection - handle different university formats
                            const isSearchUnivOfX = searchText.includes('university of');
                            const isOptionUnivOfX = optionText.includes('university of');
                            
                            // Matching patterns have priority (both "University of X" or both "X University")
                            if ((isSearchUnivOfX && isOptionUnivOfX) ||
                                (!isSearchUnivOfX && !isOptionUnivOfX && 
                                 searchText.includes('university') && optionText.includes('university'))) {
                                  
                                // If main names match after "University of"
                                if (isSearchUnivOfX && isOptionUnivOfX) {
                                    const searchMain = searchText.replace('university of', '').trim().split(',')[0];
                                    const optionMain = optionText.replace('university of', '').trim().split(',')[0];
                                    
                                    if (searchMain === optionMain) return 0.99; // Almost perfect
                                    if (optionMain.includes(searchMain) || searchMain.includes(optionMain)) return 0.9;
                                }
                                // For "X University" pattern
                                else if (searchText.includes('university') && optionText.includes('university')) {
                                    const searchPart = searchText.split('university')[0].trim();
                                    const optionPart = optionText.split('university')[0].trim();
                                    
                                    if (searchPart === optionPart) return 0.99; // Almost perfect
                                    if (optionPart.includes(searchPart) || searchPart.includes(optionPart)) return 0.9;
                                }
                            }
                            
                            // College pattern matching
                            const isSearchCollege = searchText.includes('college');
                            const isOptionCollege = optionText.includes('college');
                            if (isSearchCollege && isOptionCollege) {
                                const searchPart = searchText.split('college')[0].trim();
                                const optionPart = optionText.split('college')[0].trim();
                                
                                if (searchPart === optionPart) return 0.99; // Almost perfect
                                if (optionPart.includes(searchPart) || searchPart.includes(optionPart)) return 0.9;
                            }
                            
                            // Direct contains match
                            if (optionText.includes(mainSearchPart)) return 0.85;
                            if (mainSearchPart.includes(optionText)) return 0.75;
                            
                            // Contains match with main part before comma/dash
                            for (const part of searchParts) {
                                const trimmedPart = part.trim();
                                if (trimmedPart.length > 3 && optionText.includes(trimmedPart)) {
                                    return 0.8;
                                }
                            }
                            
                            // Word matching
                            const optWords = optionText.split(' ');
                            const searchWords = searchText.split(' ');
                            let matchedWords = 0;
                            
                            // Count important words that match (ignore common words)
                            const ignoreWords = ['the', 'and', 'of', 'or', 'for', 'in', 'at', 'a', 'an'];
                            for (const word of searchWords) {
                                if (word.length > 3 && !ignoreWords.includes(word)) {
                                    if (optWords.some(w => w.includes(word) || word.includes(w))) {
                                        matchedWords++;
                                    }
                                }
                            }
                            
                            // Calculate word match score
                            const importantWords = searchWords.filter(w => 
                                w.length > 3 && !ignoreWords.includes(w)
                            ).length;
                            
                            return importantWords > 0 ? (matchedWords / importantWords) * 0.6 : 0;
                        };
                        
                        // Find best match
                        let bestOption = null;
                        let bestScore = 0;
                        let bestMatchInfo = '';
                        let allMatches = [];
                        
                        // Try each variant against all options
                        for (const variant of variants) {
                            for (const option of options) {
                                const score = scoreMatch(option, variant);
                                
                                // Store all decent matches for logging
                                if (score > 0.5) {
                                    allMatches.push({
                                        option: option.text,
                                        variant: variant,
                                        score: score.toFixed(2)
                                    });
                                }
                                
                                if (score > bestScore) {
                                    bestScore = score;
                                    bestOption = option;
                                    bestMatchInfo = `Score: ${score.toFixed(2)} with variant: ${variant}`;
                                }
                            }
                        }
                        
                        console.log(`Best match: ${bestOption ? bestOption.text : 'none'}, ${bestMatchInfo}`);
                        console.log(`All promising matches: ${JSON.stringify(allMatches)}`);
                        
                        // Select the best option if score is good enough
                        if (bestOption && bestScore > 0.5) {
                            try {
                                // For React-select or similar components
                                const matchingOptions = Array.from(
                                    document.querySelectorAll(bestOption.element)
                                ).filter(el => el.textContent.trim() === bestOption.text);
                                
                                if (matchingOptions.length > 0) {
                                    matchingOptions[0].click();
                                    return { 
                                        success: true, 
                                        selectedOption: bestOption.text,
                                        score: bestScore
                                    };
                                }
                            } catch (e) {
                                console.error("Error clicking option:", e);
                            }
                        }
                        
                        // If we couldn't find a good match, try the first option
                        if (options.length > 0) {
                            try {
                                const firstOption = document.querySelector(options[0].element);
                                if (firstOption) {
                                    firstOption.click();
                                    return { 
                                        success: true, 
                                        selectedOption: options[0].text,
                                        fallback: true
                                    };
                                }
                            } catch (e) {
                                console.error("Error clicking first option:", e);
                            }
                        }
                        
                        return { success: false, error: "No match found" };
                    }
                    """
                    
                    result = await js_context.evaluate(js_script, {
                        "selector": selector,
                        "value": value,
                        "variants": variants,
                        "options": dropdown_options
                    })
                    
                    if result and result.get('success'):
                        selected_option = result.get('selectedOption', 'Unknown')
                        score = result.get('score', 0)
                        fallback = result.get('fallback', False)
                        
                        if fallback:
                            self.logger.warning(f"Used fallback option selection: {selected_option}")
                        else:
                            self.logger.info(f"Selected option: {selected_option} with score {score}")
                        
                        # Verify the selection
                        await asyncio.sleep(0.5)
                        selection_text = await self._verify_selection(frame, selector, selected_option)
                        
                        if selection_text:
                            self.logger.info(f"Selected value verified: {selection_text}")
                            return True
                        else:
                            self.logger.warning("Could not verify selection, may need additional confirmation")
                            return True
                
                # If JavaScript approach didn't work, try keyboard navigation
                self.logger.debug("JavaScript selection failed, trying keyboard navigation")
                await element.fill(value[:10])  # Type part of the value
                await asyncio.sleep(0.5)
                await element.press("ArrowDown")  # Press down to select first dropdown option
                await asyncio.sleep(0.2)
                await element.press("Enter")  # Press Enter to confirm
                
                # Verify the selection
                selection_text = await self._verify_selection(frame, selector, value)
                if selection_text:
                    self.logger.info(f"Selected value with keyboard: {selection_text}")
                    return True
            
            # For other field types, use a simpler approach
            for attempt in range(max_retries):
                try:
                    # Fill with original value to activate dropdown
                    await element.fill(value)
                    await asyncio.sleep(retry_delay)
                    
                    # Check if dropdown is visible
                    dropdown_visible = await self._check_dropdown_visible()
                    if dropdown_visible:
                        await self._select_first_dropdown_option()
                        return True
                    
                    # If no dropdown, just press tab to confirm
                    await element.press("Tab")
                    return True
                    
                except Exception as e:
                    self.logger.debug(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                    else:
                        raise
            
            return False
        except Exception as e:
            self.logger.warning(f"AI-assisted typeahead handling failed: {str(e)}")
            
            # Fallback: Try simple direct text entry
            try:
                element = await self.element_selector.wait_for_element(selector, frame=frame)
                if element:
                    await element.fill(value)
                    await element.press("Tab")
                    self.logger.info(f"Fallback direct text entry for {selector}")
                    return True
            except Exception as e2:
                self.logger.error(f"Even fallback failed: {str(e2)}")
                
            return False
    
    async def _type_school_name_strategically(self, element, school_name):
        """Type part of the school name in a way that's likely to show relevant options.
        
        Args:
            element: The input element
            school_name: Full school name
        """
        try:
            name_lower = school_name.lower()
            
            # General pattern-based approach - no hardcoding of specific schools
            # For "University of X" format
            if "university of " in name_lower:
                parts = name_lower.split("university of ")
                if len(parts) > 1 and parts[1]:
                    # Type "University of" plus first few chars of the university name
                    typing_value = f"University of {parts[1].split(',')[0][:3]}"
                    await element.type(typing_value, delay=20)
                    return
            
            # For "X University" format
            if "university" in name_lower and not name_lower.startswith("university"):
                parts = name_lower.split("university")
                if parts[0]:
                    # Type the first word before "University"
                    first_word = parts[0].strip().split()[0]
                    await element.type(first_word, delay=20)
                    return
                    
            # For "X College" format
            if "college" in name_lower and not name_lower.startswith("college"):
                parts = name_lower.split(" college")
                if parts[0]:
                    # Type the first word before "College"
                    first_word = parts[0].strip().split()[0]
                    await element.type(first_word, delay=20)
                    return
            
            # Default: Type the first significant word
            words = school_name.split()
            significant_words = [w for w in words if len(w) > 3 and w.lower() not in ["the", "of", "and", "at"]]
            
            if significant_words:
                await element.type(significant_words[0], delay=20)
            else:
                await element.type(school_name[:6], delay=20)
        
        except Exception as e:
            self.logger.warning(f"Strategic typing failed: {str(e)}")
            # Fallback to simple typing if strategic approach fails
            await element.type(school_name[:6], delay=20)
    
    async def _handle_discord_location_field(self, selector: str, frame=None) -> bool:
        """Special handler for Discord job portal location fields.
        
        Args:
            selector: CSS selector for the location field
            frame: Optional frame
            
        Returns:
            True if successful, False otherwise
        """
        try:
            element = await self.element_selector.wait_for_element(selector, frame=frame)
            if not element:
                return False
                
            # For Discord, first click to focus
            await element.click()
            await asyncio.sleep(0.5)
            
            # Type "San Francisco" and wait for dropdown
            await element.fill("San Francisco")
            await asyncio.sleep(1.0)
            
            # Press down arrow and enter to select first option
            await element.press("ArrowDown")
            await asyncio.sleep(0.2)
            await element.press("Enter")
            
            return True
        except Exception as e:
            self.logger.warning(f"Discord location field handling failed: {str(e)}")
            return False

    async def _is_discord_job_portal(self) -> bool:
        """
        Check if we're on the Discord job portal (Greenhouse) by looking at the URL.
        
        Returns:
            True if on Discord job portal, False otherwise
        """
        try:
            current_url = await self.browser.page.url()
            return "job-boards.greenhouse.io/discord" in current_url
        except Exception as e:
            self.logger.error(f"Error checking for Discord job portal: {str(e)}")
            return False

    async def _try_manual_fill_for_discord_school(
        self, 
        field_selector: str, 
        value: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """
        Special handling for Discord job portal school field which doesn't work like a normal typeahead.
        
        Args:
            field_selector: CSS selector for the field
            value: School name to enter
            frame_id: Optional frame ID
        
        Returns:
            True if successful, raises exception otherwise
        """
        # Get the frame to use
        frame = await self.browser.get_frame(frame_id)
        
        # First clear the field
        await frame.fill(field_selector, "")
        await asyncio.sleep(0.5)
        
        # Fill the value directly
        await frame.fill(field_selector, value)
        await asyncio.sleep(0.5)
        
        # Press Tab to move to next field
        await frame.press(field_selector, "Tab")
        
        # Verify the field has our text
        element = await frame.query_selector(field_selector)
        if element:
            input_value = await element.get_attribute("value")
            if input_value and value.lower() in input_value.lower():
                self.logger.info(f"Successfully filled Discord school field with '{value}'")
                return True
        
        # If we got here, the input wasn't set correctly
        raise Exception(f"Failed to set Discord school field value to '{value}'")

    def _quick_find_best_match(self, value: str, options: List[str]) -> Optional[str]:
        """
        Quickly find the best matching option without using LLM.
        
        Args:
            value: The value to match
            options: List of available options
            
        Returns:
            The best matching option or None
        """
        if not options:
            return None
            
        # Try exact match first (case insensitive)
        value_lower = value.lower()
        for option in options:
            if option.lower() == value_lower:
                return option
                
        # Try contains match
        for option in options:
            if value_lower in option.lower():
                return option
                
        # Try partial match (beginning of option)
        for option in options:
            if option.lower().startswith(value_lower):
                return option
                
        # Try substring match
        for option in options:
            if any(part.lower() == value_lower for part in option.lower().split()):
                return option
        
        # Use simple fuzzy matching for the rest
        best_option = None
        best_score = 0.4  # Higher threshold for faster matching
        
        for option in options:
            # Simple character-by-character comparison
            similarity = difflib.SequenceMatcher(None, option.lower(), value_lower).ratio()
            if similarity > best_score:
                best_score = similarity
                best_option = option
                
        return best_option

    async def _try_fill_and_key(self, element, text: str, key: str) -> bool:
        """
        Try to fill an input with text and then press a key.
        
        Args:
            element: The element to interact with
            text: The text to enter
            key: The key to press (Tab, Enter, etc.)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Clear existing value - use direct JS for speed
            await element.evaluate('el => el.value = ""')
            
            # Fill with new value
            await element.fill(text)
            await asyncio.sleep(0.2)  # Reduced sleep time
            
            # Press the key
            await element.press(key)
            await asyncio.sleep(0.2)  # Reduced sleep time
            
            # Check if the value was accepted (not empty)
            current_value = await element.input_value()
            return bool(current_value and current_value.strip())
        except Exception as e:
            self.logger.debug(f"Error in _try_fill_and_key: {str(e)}")
            return False
    
    async def _try_click_option_text(self, option_text: str) -> bool:
        """
        Try to click an option by its text content.
        
        Args:
            option_text: The text of the option to click
            
        Returns:
            True if successful, False otherwise
        """
        page = self.browser.page
        if not page:
            return False
            
        try:
            # Try various selector strategies
            selectors = [
                f"li:has-text('{option_text}')",
                f"[role='option']:has-text('{option_text}')",
                f".dropdown-item:has-text('{option_text}')",
                f".Select-option:has-text('{option_text}')",
                f".option:has-text('{option_text}')",
                f"div[role='listitem']:has-text('{option_text}')",
                f"span.option-label:has-text('{option_text}')"
            ]
            
            for selector in selectors:
                try:
                    # Try to find the element
                    option_element = await page.wait_for_selector(selector, timeout=500)
                    if option_element:
                        await option_element.click()
                        await asyncio.sleep(0.5)
                        return True
                except Exception:
                    continue
                    
            # Try JavaScript-based selection if direct selectors fail
            try:
                js_script = f"""
                () => {{
                    // Helper to check if element contains the text
                    const containsText = (el, searchText) => {{
                        return el.textContent.toLowerCase().includes(searchText.toLowerCase());
                    }};

                    // Find all potential dropdown options
                    const elements = Array.from(document.querySelectorAll(
                        'li, [role="option"], .dropdown-item, .select-option, ' +
                        '.option, div[role="listitem"], .Select-option, [id$="-option-0"]'
                    )).filter(el => {{
                        return el.offsetParent !== null && // Element is visible
                               containsText(el, "{option_text}");
                    }});

                    // If we have elements, click the first match
                    if (elements.length > 0) {{
                        elements[0].click();
                        return true;
                    }}
                    return false;
                }}
                """
                
                result = await page.evaluate(js_script)
                return True
                
            except Exception as e:
                self.logger.debug(f"Error in JavaScript selection: {e}")
                return False
            
        except Exception as e:
            self.logger.debug(f"Error in _try_click_option_text: {str(e)}")
            return False
            
    async def _try_intelligent_typeahead_js(self, element, value: str, variants: List[str]) -> bool:
        """
        Try to interact with typeahead using JavaScript-based intelligent selection.
        
        Args:
            element: The element to interact with
            value: The original value
            variants: List of value variants to try
            
        Returns:
            True if successful, False otherwise
        """
        page = self.browser.page
        if not page:
            return False
            
        try:
            # Fill with original value to activate dropdown
            await element.fill(value)
            await asyncio.sleep(0.5)
            
            # Get all variants to try
            all_values = [value] + [v for v in variants if v != value]
            
            # Create a JS script to find and select the best option
            js_script = f"""
            () => {{
                // Helper to find fuzzy matches
                const fuzzyMatch = (pattern, str) => {{
                    pattern = pattern.toLowerCase();
                    str = str.toLowerCase();
                    
                    // Exact match
                    if (pattern === str) return 1.0;
                    
                    // Contains match
                    if (str.includes(pattern)) return 0.8;
                    if (pattern.includes(str)) return 0.7;
                    
                    // Initial substring match
                    if (str.startsWith(pattern)) return 0.6;
                    if (pattern.startsWith(str)) return 0.5;
                    
                    // Character-by-character matching (simple)
                    let score = 0;
                    let matched = 0;
                    const len = Math.min(pattern.length, str.length);
                    
                    for (let i = 0; i < len; i++) {{
                        if (pattern[i] === str[i]) matched++;
                    }}
                    
                    if (len > 0) score = matched / len * 0.4;
                    return score;
                }};
                
                // Values to try
                const valuesToTry = {all_values[:5]};
                
                // Find all visible dropdown options
                const getVisibleOptions = () => {{
                    return Array.from(document.querySelectorAll(
                        'li, [role="option"], .dropdown-item, .select-option, ' +
                        '.option, div[role="listitem"], span.option-label, .Select-option, ' +
                        '.autocomplete-option, .typeahead-option, .suggestion-item'
                    )).filter(el => {{
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && 
                               style.visibility !== 'hidden' &&
                               rect.width > 0 &&
                               rect.height > 0;
                    }});
                }};
                
                const options = getVisibleOptions();
                if (!options.length) return false;
                
                // Find best match among all options for any of our variants
                let bestMatch = null;
                let bestScore = 0;
                
                for (const option of options) {{
                    const optionText = option.textContent.trim();
                    if (!optionText) continue;
                    
                    for (const val of valuesToTry) {{
                        const score = fuzzyMatch(val, optionText);
                        if (score > bestScore) {{
                            bestScore = score;
                            bestMatch = option;
                        }}
                    }}
                }}
                
                // Click the best match if score is good enough
                if (bestMatch && bestScore >= 0.5) {{
                    bestMatch.click();
                    return true;
                }}
                
                return false;
            }}
            """
            
            result = await page.evaluate(js_script)
            return bool(result)
            
        except Exception as e:
            self.logger.debug(f"Error in _try_intelligent_typeahead_js: {str(e)}")
            return False
    
    def _generate_general_selection_variants(self, value: str, field_type: str) -> List[str]:
        """
        Generate variants for general selection fields like gender, ethnicity, etc.
        
        Args:
            value: The original value
            field_type: The type of field (gender, ethnicity, etc.)
            
        Returns:
            List of variants for the selection
        """
        variants = [value]
        
        value_lower = value.lower()
        
        # Add common forms regardless of the specific field type
        variants.extend([
            value,
            value.title(),
            value.lower(),
            value.upper()
        ])
        
        # Add field-specific variations based on common patterns rather than hardcoded lists
        if field_type == 'gender':
            # Common gender options
            if 'male' in value_lower and 'fe' not in value_lower:
                variants.extend(['Male', 'M'])
            elif 'female' in value_lower or ('fe' in value_lower and 'male' in value_lower):
                variants.extend(['Female', 'F'])
            elif 'non' in value_lower and ('binary' in value_lower or 'conform' in value_lower):
                variants.extend(['Non-binary', 'Nonbinary', 'Non-conforming', 'Other'])
            elif 'decline' in value_lower or 'prefer' in value_lower or 'not' in value_lower:
                variants.extend(['Decline to state', 'Prefer not to say', 'Not specified'])
                
        elif field_type == 'ethnicity':
            # Common ethnicity options based on patterns
            if 'hispanic' in value_lower or 'latino' in value_lower:
                variants.extend(['Hispanic or Latino', 'Hispanic/Latino'])
            elif 'white' in value_lower or 'caucasian' in value_lower:
                variants.extend(['White', 'Caucasian', 'White/Caucasian'])
            elif 'black' in value_lower or 'african' in value_lower:
                variants.extend(['Black', 'African American', 'Black or African American'])
            elif 'asian' in value_lower:
                variants.extend(['Asian', 'Asian American'])
            elif 'native' in value_lower and ('american' in value_lower or 'alaska' in value_lower):
                variants.extend(['Native American', 'American Indian', 'Alaska Native', 'Native American or Alaska Native'])
            elif 'pacific' in value_lower or 'hawaiian' in value_lower:
                variants.extend(['Pacific Islander', 'Native Hawaiian', 'Native Hawaiian or Pacific Islander'])
            elif 'two' in value_lower or 'multiple' in value_lower or 'mixed' in value_lower:
                variants.extend(['Two or More Races', 'Multiple Races', 'Mixed Race', 'Multiracial'])
            elif 'decline' in value_lower or 'prefer' in value_lower or 'not' in value_lower:
                variants.extend(['Decline to state', 'Prefer not to say', 'Not specified'])
                
        elif field_type == 'disability':
            # Common disability response options
            if any(yes_term in value_lower for yes_term in ['yes', 'have', 'disabled', 'disability']):
                variants.extend(['Yes', 'Yes, I have a disability', 'I have a disability'])
            elif any(no_term in value_lower for no_term in ['no', 'don\'t', 'do not', 'none']):
                variants.extend(['No', 'No, I don\'t have a disability', 'I do not have a disability'])
            elif 'decline' in value_lower or 'prefer' in value_lower or 'not' in value_lower:
                variants.extend(['Decline to state', 'Prefer not to say', 'I don\'t wish to answer'])
                
        elif field_type == 'veteran':
            # Common veteran response options
            if any(yes_term in value_lower for yes_term in ['yes', 'am', 'protected', 'veteran']):
                variants.extend(['Yes', 'Yes, I am a veteran', 'Protected veteran', 'I am a protected veteran'])
            elif any(no_term in value_lower for no_term in ['no', 'not', 'none']):
                variants.extend(['No', 'No, I am not a veteran', 'I am not a protected veteran'])
            elif 'decline' in value_lower or 'prefer' in value_lower or 'not' in value_lower:
                variants.extend(['Decline to state', 'Prefer not to say', 'I don\'t wish to answer'])
                
        elif field_type == 'selection':
            # Generic selection field - common patterns for yes/no, true/false, etc.
            if value_lower in ['yes', 'y', 'true', 't']:
                variants.extend(['Yes', 'Y', 'True', 'T', '1'])
            elif value_lower in ['no', 'n', 'false', 'f']:
                variants.extend(['No', 'N', 'False', 'F', '0'])
        
        # De-duplicate the list while maintaining order
        seen = set()
        unique_variants = []
        for item in variants:
            if item and item not in seen:
                seen.add(item)
                unique_variants.append(item)
                
        return unique_variants

    def _generate_school_variants(self, school_name: str) -> List[str]:
        """Generate intelligent variants for school/university names without hardcoding specific schools.
        
        Args:
            school_name: Original school name
            
        Returns:
            List of variant forms for the school name
        """
        variants = [school_name]  # Always include original value
        
        # Don't process empty or very short names
        if not school_name or len(school_name) < 3:
            return variants
        
        # Lowercase for comparison
        name_lower = school_name.lower()
        name_words = name_lower.split()
        
        # Handle various university formats
        
        # 1. "University of X" format
        if "university of " in name_lower:
            base_name = name_lower.replace("university of ", "").strip()
            
            # Generate variants with different separators
            variants.extend([
                f"University of {base_name.title()}",
                f"University of {base_name.title().replace(',', '')}",
                f"University of {base_name.title().replace(',', ' -')}",
                f"University of {base_name.title().replace('-', ',')}",
                f"U of {base_name.title()}",
                base_name.title()
            ])
            
            # Split by comma, hyphen, or other separators
            split_parts = re.split(r'[,\-–\(\)]', base_name)
            if len(split_parts) > 1:
                main_part = split_parts[0].strip()
                location = split_parts[1].strip()
                
                # Add location-based variants
                variants.extend([
                    f"University of {main_part.title()} - {location.title()}",
                    f"University of {main_part.title()}, {location.title()}",
                    f"University of {main_part.title()} {location.title()}",
                    location.title(),
                    f"{location.title()} University"
                ])
                
                # Add abbreviation for University of X
                if len(main_part) > 0:
                    variants.append(f"U{main_part[0].upper()}")
                    
                # Special case for University of California campuses
                if "california" in main_part:
                    campus_name = location.title() if location else ""
                    if campus_name:
                        variants.extend([
                            f"UC {campus_name}",
                            f"University of California {campus_name}",
                            f"University of California - {campus_name}",
                            f"University of California, {campus_name}"
                        ])
        
        # 2. "X University" format
        elif "university" in name_lower and not name_lower.startswith("university"):
            # Extract the name part before "University"
            parts = name_lower.split("university")
            base_name = parts[0].strip()
            
            variants.extend([
                f"{base_name.title()} University",
                base_name.title()
            ])
            
        # 3. "Institute of Technology" format
        elif "institute of technology" in name_lower or "polytechnic" in name_lower:
            base_name = re.sub(r'institute of technology|polytechnic', '', name_lower).strip()
            
            variants.extend([
                f"{base_name.title()} Institute of Technology",
                f"{base_name.title()} Tech",
                base_name.title()
            ])
        
        # 4. Add common format variations and abbreviations
        
        # Generate initials for multi-word names
        if len(name_words) > 1:
            initials = ''.join(word[0].upper() for word in name_words)
            if len(initials) > 1:  # Only add if we have meaningful initials
                variants.append(initials)
                
                # Add "U" prefix for universities
                if "university" in name_lower:
                    variants.append(f"{initials}U")
        
        # Add variants with different punctuation and spacing
        clean_name = re.sub(r'[^\w\s]', ' ', school_name)
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        if clean_name != school_name:
            variants.append(clean_name)
        
        # Add hyphen/comma variations
        variants.append(school_name.replace(",", " -"))
        variants.append(school_name.replace(" -", ","))
        
        # Extract short prefix for dropdown activation
        if len(school_name) > 3:
            variants.append(school_name[:3])
        
        return variants

    def _generate_degree_variants(self, degree: str) -> List[str]:
        """Generate variants of degree names for better matching.
        
        Args:
            degree: The degree name
            
        Returns:
            List of variants
        """
        variants = []
        degree_lower = degree.lower()
        
        # Add original degree
        variants.append(degree)
        
        # Add common degree variants
        if "bachelor" in degree_lower or "bs" in degree_lower or "b.s." in degree_lower:
            variants.extend([
                "Bachelor of Science",
                "Bachelor's Degree",
                "Bachelor's degree",
                "BS",
                "B.S.",
                "Bachelor",
                "Bachelors",
                "Bachelor's"
            ])
        elif "master" in degree_lower or "ms" in degree_lower or "m.s." in degree_lower:
            variants.extend([
                "Master of Science",
                "Master's Degree",
                "Master's degree",
                "MS",
                "M.S.",
                "Master",
                "Masters",
                "Master's"
            ])
        elif "phd" in degree_lower or "ph.d" in degree_lower or "doctor" in degree_lower:
            variants.extend([
                "PhD",
                "Doctor of Philosophy",
                "Ph.D.",
                "Doctorate",
                "Doctoral Degree",
                "Doctoral degree"
            ])
        elif "associate" in degree_lower or "aa" in degree_lower or "a.a." in degree_lower:
            variants.extend([
                "Associate Degree",
                "Associate's Degree",
                "Associate's degree",
                "AA",
                "A.A.",
                "Associate",
                "Associates",
                "Associate's"
            ])
            
        # Add general "degree" variants that will match with any degree type
        variants.extend([
            "Degree",
            "degree",
            "Any Degree",
            "College Degree",
            "Diploma"
        ])
            
        return variants

    def _generate_location_variants(self, location: str) -> List[str]:
        """Generate intelligent variants for location fields.
        
        Args:
            location: Original location string
            
        Returns:
            List of variant forms for the location
        """
        variants = set()
        if not location or len(location) < 3:
            return list(variants)
        
        # Original value is always included
        variants.add(location)
        
        # Parse the location components
        city = state = country = ""
        
        # Handle "City, State" format (like "San Francisco, CA")
        city_state_match = re.match(r'([^,]+),\s*([A-Z]{2}|[^,]+)$', location)
        
        # Handle "City, State, Country" format (like "San Francisco, California, USA")
        city_state_country_match = re.match(r'([^,]+),\s*([^,]+),\s*([^,]+)$', location)
        
        if city_state_country_match:
            city, state, country = [x.strip() for x in city_state_country_match.groups()]
            
            # Add city only
            variants.add(city)
            
            # Add city, state
            variants.add(f"{city}, {state}")
            
            # Add state only
            variants.add(state)
            
            # Handle US state codes
            if country.upper() in ["USA", "US", "UNITED STATES"]:
                # If state is a full name, add state code variant
                us_state_map = {
                    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
                    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
                    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
                    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
                    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
                    "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
                    "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
                    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
                    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
                    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY"
                }
                
                state_lower = state.lower()
                if state_lower in us_state_map:
                    state_code = us_state_map[state_lower]
                    variants.add(f"{city}, {state_code}")
                elif len(state) == 2:  # It's already a state code
                    # Try to find the full state name
                    reverse_map = {v: k for k, v in us_state_map.items()}
                    if state.upper() in reverse_map:
                        full_state = reverse_map[state.upper()].title()
                        variants.add(f"{city}, {full_state}")
        
        elif city_state_match:
            city, state = [x.strip() for x in city_state_match.groups()]
            
            # Add city only
            variants.add(city)
            
            # Add state only
            variants.add(state)
            
            # For US locations, handle state codes similarly
            if len(state) == 2 and state.upper() == state:  # Looks like a state code
                variants.add(city)  # City alone is often accepted
        
        # No comma found, assume it's a city or simple location
        else:
            # No additional variants needed for simple locations
            pass
        
        return list(variants) 

    async def select_typeahead_option_by_mouse(self, selector: str, frame=None) -> bool:
        """Select the first option from a typeahead dropdown using mouse interaction.
        
        Args:
            selector: CSS selector for the input field
            frame: Optional frame
            
        Returns:
            True if successful, False otherwise
        """
        try:
            option_selectors = [
                ".select__option", 
                "[role='option']", 
                ".dropdown-item",
                "li.select-option",
                ".typeahead-option"
            ]
            
            for option_selector in option_selectors:
                try:
                    # Find all dropdown options
                    page = frame or await self.browser.page
                    options = await page.query_selector_all(option_selector)
                    
                    if options and len(options) > 0:
                        # Click the first visible option
                        for option in options:
                            is_visible = await option.is_visible()
                            if is_visible:
                                await option.click()
                                self.logger.info(f"Selected dropdown option using selector: {option_selector}")
                                await asyncio.sleep(0.2)
                                return True
                except Exception as e:
                    self.logger.debug(f"Failed to select using {option_selector}: {str(e)}")
                    
            return False
        except Exception as e:
            self.logger.debug(f"Mouse selection failed: {str(e)}")
            return False

    # --- Placeholder methods for new interaction strategies --- 

    async def type_and_select_option_exact(self, selector: str, value: str, frame_id_str: Optional[str] = None) -> bool:
        """Strategy: Type into field and select the exact matching option."""
        element = None
        frame = None
        try:
            # Correctly get frame object and frame_id string
            frame = await self.browser.get_frame(frame_id_str) if frame_id_str else self.browser.page
            if not frame:
                 self.logger.error(f"Failed to get frame object: {frame_id_str or 'main'}")
                 return False
                 
            # Use element_selector with the frame_id string
            element = await self.element_selector.find_element(selector, frame_id=frame_id_str) 
            
            if not element:
                self.logger.error(f"Element not found for selector: {selector} in frame: {frame_id_str or 'main'}")
                return False

            # --- Subsequent logic uses the frame object for interactions --- 

            # Type the value into the input field
            await element.fill(value) 
            self.logger.debug(f"Typed value '{value}' into {selector}")
            
            # Wait a bit longer for dropdown options to potentially appear
            # Still might need refinement based on specific site behavior
            await frame.wait_for_timeout(1000) # 1000ms wait

            # Construct selector for the clickable option containing the exact text
            # Revert to broader :is() selector and escape the value for CSS safety
            escaped_value = self._escape_css_string(value) # Escape the value
            option_container_selector = f":is([role='option'], .select-option, .dropdown-item, li):has-text('{escaped_value}')"
            
            self.logger.debug(f"Attempting to find exact match option container with selector: {option_container_selector}")
            
            # Find the container element
            option_element = await frame.query_selector(option_container_selector)
            
            if option_element and await option_element.is_visible():
                try:
                    # Click the container element
                    await option_element.click(timeout=5000) # Add a shorter timeout for the click itself
                    self.logger.info(f"Clicked exact match option container for {selector} with text: {value}")
                    return True
                except Exception as click_exc:
                    self.logger.warning(f"Click failed on option container for {selector} ({value}): {str(click_exc)}")
                    # Proceed to fallback if click fails
            
            # If element not found, not visible, or click failed, log warning and fallback
            self.logger.warning(f"Could not find or click visible exact match option container for {selector} with text: {value}. Selector used: {option_container_selector}")
            # Fallback should indicate failure, not success
            # await element.fill(value) # Re-fill just in case - Remove this, it doesn't help
            # await frame.press("body", "Tab") # Try tabbing away to confirm - Remove this
            # self.logger.debug(f"Fallback: Re-filled {selector} and tabbed away.") - Remove this
            return False # Indicate failure if we couldn't click the option

        except Exception as e:
            self.logger.error(f"Error in type_and_select_option_exact for selector {selector}: {str(e)}")
            self.logger.debug(traceback.format_exc())
            return False

    async def type_and_select_option_fuzzy(self, selector: str, value: str, frame_id_str: Optional[str] = None, threshold: float = 0.75) -> bool:
        """Strategy: Type into field simulating user input and select the best fuzzy matching visible option."""
        element = None
        frame = None
        best_match_text = None # Initialize here
        try:
            # 1. Get Element and Frame
            frame = await self.browser.get_frame(frame_id_str) if frame_id_str else self.browser.page
            if not frame:
                 self.logger.error(f"Fuzzy: Failed to get frame object: {frame_id_str or 'main'}")
                 return False

            element = await self.element_selector.find_element(selector, frame_id=frame_id_str)
            if not element:
                self.logger.error(f"Fuzzy: Element not found for selector: {selector} in frame: {frame_id_str or 'main'}")
                return False

            # 2. Type Value with Delay
            self.logger.debug(f"Fuzzy: Typing value '{value}' into {selector} with delay...")
            await element.type(value, delay=100) # Simulate typing
            self.logger.debug(f"Fuzzy: Finished typing '{value}'.")

            # 3. Wait briefly and attempt to find/click best fuzzy match
            await frame.wait_for_timeout(750) # Wait for options to likely appear
            
            # --- REFACTOR: Use _find_and_click_option helper --- 
            self.logger.debug(f"Fuzzy: Attempting to find and click best fuzzy option for '{value}' using helper.")
            option_clicked = await self._find_and_click_option(frame, value, exact_match=False)

            if option_clicked:
                 # Dismissal is handled within _find_and_click_option now
                 # Verify selection after successful click
                 if await verify_input_value(frame, selector, value, threshold=VERIFICATION_THRESHOLD):
                      self.logger.info(f"Fuzzy selection for '{value}' successful and verified.")
                      return True
                 else:
                      self.logger.warning(f"Fuzzy selection clicked '{value}' but failed verification.")
                      # If click succeeded but verification failed, it might still be the intended action
                      # Consider returning True here if the click itself was the goal, 
                      # or False if verification is critical.
                      return False # Sticking with False if verification fails for now.
            # --- END REFACTOR ---
            else:
                # --- REMOVE/SIMPLIFY KEYBOARD FALLBACK --- 
                # The _find_and_click_option helper is now more robust. 
                # If it fails, a blind keyboard nav is unlikely to succeed reliably and adds complexity.
                # Consider removing it entirely or making it a last-resort debug option.
                self.logger.warning(f"Fuzzy: Helper '_find_and_click_option' could not find/click a suitable option for '{value}'. Failing strategy.")
                # Optional: Keep dismissal attempt just in case something opened
                await self._try_dismiss_dropdown(element, frame)
                return False
                # --- END KEYBOARD FALLBACK REMOVAL ---

        except Exception as e:
            self.logger.error(f"Fuzzy: Unexpected error during type and select for {selector}: {str(e)}")
            self.logger.debug(traceback.format_exc())
            # Attempt dismissal on general failure
            if frame and element:
                 await self._try_dismiss_dropdown(element, frame)
            return False

    async def fill_and_confirm_field(self, selector: str, value: str, frame_id: Optional[str] = None) -> bool:
        """Strategy: Fill the field and then potentially tab or click away to confirm."""
        self.logger.debug(f"Attempting fill_and_confirm_field for {selector}")
        success = await self.fill_field(selector, value, frame_id)
        if success:
            # Try pressing Tab to confirm/move focus
            try:
                frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
                element = await self.element_selector.find_element(selector, frame_id=frame_id)
                if element:
                    await element.press('Tab')
                    self.logger.debug(f"Pressed Tab after filling {selector} to confirm.")
                    await asyncio.sleep(0.2) # Small delay after tab
            except Exception as e:
                self.logger.warning(f"Failed to press Tab after filling {selector}: {e}")
        return success

    async def clear_type_and_select_option(self, selector: str, value: str, frame_id: Optional[str] = None) -> bool:
        """Strategy: Clear the field, type value, and select the matching option (fuzzy)."""
        self.logger.debug(f"Attempting clear_type_and_select_option for {selector}")
        try:
            await self.clear_field(selector, frame_id) # Clear first
            # Now perform the type and select fuzzy logic
            return await self.type_and_select_option_fuzzy(selector, value, frame_id)
        except Exception as e:
            self.logger.error(f"Error during clear_type_and_select_option for {selector}: {e}")
            return False

    # --- End Placeholder methods ---

    async def clear_field(self, selector: str, frame_id: Optional[str] = None) -> None:
        """Clear the content of an input field."""
        try:
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            if frame:
                await frame.locator(selector).clear()
                self.logger.debug(f"Cleared field: {selector}")
        except Exception as e:
            self.logger.error(f"Error clearing field {selector}: {str(e)}")

    async def select_option_from_list(
        self,
        selector: str,
        value: str,
        available_options: List[Union[str, Dict[str, str]]],
        frame_id_str: Optional[str] = None,
        threshold: float = 0.80 # Stricter threshold for pre-scraped list
    ) -> bool:
        """Selects an option from a provided list using fuzzy matching.

        This method is intended for cases where options have been pre-scraped
        (e.g., by FormAnalyzerAgent) and passed to the handler, avoiding
        the need for live scraping within this interaction.

        Args:
            selector: CSS selector of the input/trigger element (used mainly for logging).
            value: The desired value to match.
            available_options: A list of option strings or dicts (e.g., [{'value': '...', 'text': '...'}])
            frame_id_str: Optional frame ID string (used mainly for logging).
            threshold: The minimum similarity ratio for a match (0.0 to 1.0).

        Returns:
            True if a match was found and selected, False otherwise.
        """
        self.logger.info(f"Attempting selection from pre-scraped list for '{selector}'. Desired value: '{value}'")

        if not available_options:
            self.logger.warning(f"No available options provided for selector '{selector}'. Cannot select from list.")
            return False

        option_texts: List[str] = []
        option_map: Dict[str, Union[str, Dict]] = {} # Map normalized text back to original option

        # Normalize and extract text from options
        for option in available_options:
            text = ""
            if isinstance(option, str):
                text = option
            elif isinstance(option, dict):
                # Prioritize 'text' key, fallback to 'label', then 'value'
                text = option.get('text', option.get('label', option.get('value', '')))

            if text: # Only consider options with non-empty text
                normalized_text = text.strip().lower()
                if normalized_text: # Avoid empty strings after stripping
                    option_texts.append(normalized_text)
                    # Store mapping from normalized text to original option structure or text
                    option_map[normalized_text] = option

        if not option_texts:
            self.logger.warning(f"Could not extract valid text from available_options for '{selector}'.")
            return False

        normalized_value = value.strip().lower()

        # Use difflib to find the best match
        # get_close_matches returns a list of matches above the cutoff
        matches = difflib.get_close_matches(normalized_value, option_texts, n=1, cutoff=threshold)

        if matches:
            best_match_normalized = matches[0]
            original_option = option_map[best_match_normalized] # Get the original option structure/text

            # Determine the actual text to log/use from the original option
            actual_option_text = ""
            if isinstance(original_option, str):
                actual_option_text = original_option
            elif isinstance(original_option, dict):
                actual_option_text = original_option.get('text', original_option.get('label', original_option.get('value', best_match_normalized)))

            self.logger.info(f"Found best match '{actual_option_text}' for '{value}' in pre-scraped list with ratio >= {threshold}.")

            # --- Placeholder for actual selection ---
            # In a real scenario, you might need to find the element corresponding
            # to `actual_option_text` and click it. However, this method's purpose
            # is primarily the *matching* against a pre-scraped list.
            # The calling handler (e.g., TextActionHandler) would still need to
            # use a strategy (like fill, or type_and_select) based on this match result.
            # For now, we return True indicating a match was found.
            # Consider returning the matched text instead of bool if the caller needs it.
            # TODO: Clarify if this method should also perform the click, or just return the match.
            # Assuming for now it just confirms a match exists.
            return True # Indicate a suitable match was found
        else:
            self.logger.warning(f"No suitable match found for '{value}' in pre-scraped list for '{selector}' (threshold: {threshold}). Options considered: {option_texts[:10]}...")
            return False

    async def _try_dismiss_dropdown(self, element, frame) -> None:
        """Attempts to dismiss an open dropdown, usually by clicking the body or pressing Escape."""
        try:
            self.logger.debug("Attempting to dismiss dropdown (if any) with Escape key.")
            # --- CHANGE: Target the input element instead of body ---
            if element:
                 await element.press("Escape", timeout=1000) # Add small timeout
            else:
                 # Fallback to body if element is somehow lost
                 self.logger.debug("Input element not available for Escape key, falling back to body.")
                 await frame.press("body", "Escape", timeout=1000)
            await asyncio.sleep(0.1) # Short delay
            self.logger.debug("Dropdown dismissal attempt finished (Escape key).")
        except Exception as e:
            # Use element selector in log message if available
            log_selector = "unknown element" 
            if element and hasattr(element, '__str__'): # Check if element is usable
                try:
                     log_selector = str(await element.evaluate('el => el.outerHTML.split(">", 1)[0] + ">'))
                except Exception:
                     pass # Ignore evaluation errors
            self.logger.warning(f"Failed to dismiss dropdown for {log_selector}: {str(e)}")


# --- Placeholder/Legacy/Reference methods to be reviewed/removed later --- #

    # Note: The following methods (_get_dropdown_options_advanced, etc.) seem like older attempts
    # or highly specialized logic (e.g., for Greenhouse). They should be reviewed 
    # against the newer strategy-based approach and refactored/removed if redundant.

    async def _get_dropdown_options_advanced(self, frame, selector: str, value: str) -> Optional[List[Dict[str, Any]]]:
        """Advanced method to handle complex dropdowns, potentially using JS or specific selectors.
           [CONSIDER FOR REFACTOR/REMOVAL - Superseded by general strategies?]
        """
        self.logger.debug(f"Advanced dropdown option retrieval for {selector}")
        # ... (Implementation likely involves clicking, waiting, complex scraping) ...
        # Example Sketch:
        # try:
        #     element = await self.element_selector.find_element(selector, frame)
        #     await element.click() 
        #     await frame.wait_for_timeout(500) # Wait for options
        #     options = await frame.locator('.dropdown-option-class').all()
        #     return [{ "text": await opt.text_content(), "value": await opt.get_attribute('data-value') } for opt in options]
        # except Exception as e:
        #     self.logger.warning(f"Advanced option retrieval failed for {selector}: {e}")
        #     return None
        return None # Placeholder

    # Other legacy/reference methods can follow here...
    # _extract_options_via_js
    # _handle_greenhouse_dropdown
    # _find_option_element
    # _normalize_option_text
    # etc.

# --- End Placeholder/Legacy section --- #