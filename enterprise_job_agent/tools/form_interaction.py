"""Tools for interacting with form elements."""

import asyncio
import difflib
import logging
import traceback
import os
import re
import time
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from difflib import SequenceMatcher

from thefuzz import fuzz

from enterprise_job_agent.core.browser_interface import BrowserInterface
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from enterprise_job_agent.core.exceptions import ActionExecutionError
from enterprise_job_agent.tools.constants import (DEFAULT_FUZZY_THRESHOLD, 
                                                HIGH_FUZZY_THRESHOLD,
                                                INTERACTION_DELAY, 
                                                POST_CLICK_DELAY, 
                                                POST_TYPE_DELAY,
                                                RETRY_DELAY_BASE, 
                                                SHORT_TIMEOUT,
                                                VERIFICATION_THRESHOLD, 
                                                VISIBILITY_TIMEOUT)
from enterprise_job_agent.tools.element_selector import ElementSelector
from enterprise_job_agent.tools.verification_helper import verify_input_value, verify_selection

logger = logging.getLogger(__name__)

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
    """Handles form interactions with retries and error handling."""
    
    def __init__(
        self,
        browser_manager: BrowserInterface,
        element_selector: ElementSelector,
        diagnostics_manager: Optional[DiagnosticsManager] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize the FormInteraction class."""
        self.browser = browser_manager
        self.element_selector = element_selector
        self.diagnostics_manager = diagnostics_manager
        self.config = config or {}
        self.logger = logger
        
        # Set default retry configuration
        self.max_retries = self.config.get('max_retries', 3)
        self.retry_delay = self.config.get('retry_delay', RETRY_DELAY_BASE)
    
    def _log(self, level: str, message: str) -> None:
        """Log a message using the diagnostics manager if available."""
        if not self.diagnostics_manager:
            return
            
        log_method = getattr(self.diagnostics_manager, level, None)
        if log_method:
            log_method(message)
    
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
    
    async def fill_field(
        self,
        selector: str,
        value: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Fill a field with a value."""
        try:
            element = await self.element_selector.find_element(selector, frame_id)
            if element:
                try:
                    await element.fill("")
                except Exception as e:
                    self.logger.debug(f"Failed to clear field '{selector}': {e}")
                    
                await element.type(value)
                self._log("debug", f"Filled field {selector} with value: {value}")
                return True
            else:
                # Try using direct frame fill
                frame = await self.browser.get_frame(frame_id)
                if frame:
                    try:
                        await frame.fill(selector, value)
                        self._log("debug", f"Filled field {selector} with direct frame.fill: {value}")
                        return True
                    except Exception as e:
                        self._log("error", f"Failed to fill field in frame: {selector} - {str(e)}")
                else:
                    raise ActionExecutionError(f"Failed to find field '{selector}' for filling")
        except ActionExecutionError:
             raise
        except Exception as e:
            self._log("error", f"Error filling field {selector}: {str(e)}")
            raise ActionExecutionError(f"Unexpected error filling field {selector}: {e}") from e
    
    async def select_option(
        self,
        selector: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
        frame_id: Optional[str] = None
    ) -> bool:
        """Select an option from a dropdown with enhanced handling."""
        if value is None and label is None:
            self.logger.error("select_option requires either 'value' or 'label'")
            return False
            
        target_text = label if label is not None else value
        log_value = f"label='{label}'" if label is not None else f"value='{value}'"
        log_target = f"'{selector}' with {log_value}"
        self.logger.debug(f"Attempting select_option for {log_target}")

        try:
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            if not frame:
                self._log("error", f"Failed to get frame for select_option: {frame_id}")
                return False
            
            # 1. Try standard select_option
            if label is not None:
                 try:
                    await frame.select_option(selector, label=label, timeout=SHORT_TIMEOUT)
                    self._log("debug", f"Selected option by label: {label}")
                     if await verify_selection(frame, selector, label):
                         return True
                 except Exception as e:
                    self._log("debug", f"Failed standard select by label: {e}")
            
            if value is not None:
                 try:
                    await frame.select_option(selector, value=value, timeout=SHORT_TIMEOUT)
                    self._log("debug", f"Selected option by value: {value}")
                     if await verify_selection(frame, selector, value):
                         return True
                 except Exception as e:
                    self._log("debug", f"Failed standard select by value: {e}")
            
            # 2. Try custom dropdown handling
            self.logger.debug(f"Trying custom interaction for {log_target}")
            
            # Get the element 
            element = await self.element_selector.find_element(selector, frame_id=frame.url)
            if not element:
                self._log("error", f"Failed to find element '{selector}'")
                return False
            
            # Click to open the dropdown
            try:
                await element.click(timeout=3000)
                self._log("debug", f"Clicked element to open dropdown")
                await asyncio.sleep(0.5)
            except Exception as click_err:
                self.logger.warning(f"Failed to click element: {click_err}")
            
            # Try to find and click matching option
            result = await self._click_dropdown_option(element, target_text)
            if result:
                self._log("debug", f"Clicked option matching '{target_text}'")
                if await verify_selection(frame, selector, target_text):
                    return True
            
            # Try typing + Enter
            try:
                await element.fill("")
                await element.type(target_text, delay=50)
                self._log("debug", f"Typed '{target_text}' into element")
                await asyncio.sleep(0.7)
                
                await element.press("Enter")
                self._log("debug", f"Pressed Enter")
                await asyncio.sleep(0.5)
                
                if await verify_selection(frame, selector, target_text):
                    return True
            except Exception as type_err:
                self.logger.warning(f"Error during type/enter: {type_err}")

            self._log("error", f"Failed to select option for {log_target}")
            return False
            
        except Exception as e:
            self._log("error", f"Unexpected error in select_option: {e}")
            return False
    
    async def _click_dropdown_option(self, element, value, options: list = None, field_type: str = None):
        """Find and click the best matching dropdown option.
        
        This method tries to find the most similar option to the provided value
        and click on it, handling various dropdown implementations.
        
        Args:
            element: The dropdown element
            value: The value to select
            options: Optional pre-found options list
            field_type: Type of field (school, location, etc.) to use appropriate matching
        
        Returns:
            True if an option was successfully clicked, False otherwise
        """
        if not element or not value:
            return False
        
        # Import variant generator here to avoid circular imports
        try:
            # Absolute import
            from enterprise_job_agent.tools.variant_generator import generate_answer_variants
        except ImportError:
            logger.debug("Failed to import variant_generator using absolute path")
            # Last resort - get module from file
            import importlib.util
            import os
            spec = importlib.util.spec_from_file_location(
                "variant_generator", 
                os.path.join(os.path.dirname(__file__), "variant_generator.py")
            )
            variant_generator = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(variant_generator)
            generate_answer_variants = variant_generator.generate_answer_variants
        
        value = str(value).strip()
        logger.debug(f"Attempting to click dropdown option: {value}")
        
        try:
            # Find all options if not provided
            if not options:
                # Try to find options using various selectors
                await self.click_element(element)  # Ensure dropdown is open
                
                # Define dropdown option selectors if not already defined
                dropdown_selectors = getattr(self, 'dropdown_option_selectors', [
                    "[role=option]", 
                    "li[role=option]",
                    "div[role=option]", 
                    ".dropdown-item",
                    ".select-option",
                    "li.option",
                    "li"
                ])
                
                options = []
                for selector in dropdown_selectors:
                    try:
                        # Wait briefly for options to appear
                        frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
                        await frame.wait_for_selector(selector, timeout=1000)
                        option_elements = await frame.query_selector_all(selector)
                        if option_elements:
                            options.extend(option_elements)
                            break
                except Exception as e:
                        logger.debug(f"Error finding options with selector {selector}: {e}")
            
            if not options:
                logger.warning("No dropdown options found to click")
                return False
            
            # Generate variants of the target value based on field type
            value_variants = generate_answer_variants(value, field_type)
            logger.debug(f"Generated variants for matching: {value_variants}")
            
            # Find best matching option
                best_match = None
                best_score = 0
            threshold = 65  # Minimum similarity score (0-100)
                    
                    for option in options:
                try:
                        option_text = await option.text_content()
                    option_text = option_text.strip() if option_text else ""
                    
                    # Skip empty options or ones that are clearly separators
                    if not option_text or option_text == '-' or len(option_text) < 2:
                            continue
                        
                    # Calculate similarity using fuzzywuzzy for each variant
                    for variant in value_variants:
                        # Use local calculation or imported fuzzywuzzy
                        try:
                            from fuzzywuzzy import fuzz
                            similarity = fuzz.token_sort_ratio(variant.lower(), option_text.lower())
                        except ImportError:
                            # Fallback to basic similarity if fuzzywuzzy not available
                            similarity = self._calculate_basic_similarity(variant.lower(), option_text.lower())
                        
                        # Boost exact matches and starts-with matches
                        if option_text.lower() == variant.lower():
                            similarity = 100
                        elif option_text.lower().startswith(variant.lower()):
                            similarity += 15
                            
                        if similarity > best_score:
                            best_score = similarity
                            best_match = option
                            if similarity == 100:
                                break  # Perfect match found
                                
                    if best_score == 100:
                        break  # Perfect match found in outer loop
                    
            except Exception as e:
                    logger.debug(f"Error processing option: {e}")
                    
            if best_match and best_score >= threshold:
                option_text = await best_match.text_content()
                option_text = option_text.strip() if option_text else ""
                logger.info(f"Selected option '{option_text}' with match score: {best_score}")
                
                # Attempt to click the best matching option using multiple methods
                try:
                    # Method 1: Normal click
                    await self.click_element(best_match)
                    
                    # Verify the selection worked by checking if dropdown is closed
                    is_closed = await self._verify_dropdown_closed(dropdown_selectors)
                    if is_closed:
                        logger.debug("Dropdown successfully closed after selection")
                return True
            
                    # Method 2: JavaScript click if normal click didn't work
                    frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
                    await frame.evaluate('el => el.click()', best_match)
                    
                    # Check again if dropdown closed
                    is_closed = await self._verify_dropdown_closed(dropdown_selectors)
                    if is_closed:
                        logger.debug("Dropdown closed after JavaScript click")
                return True
                
                    # Method 3: Force click with position if needed
                    try:
                        await best_match.click(force=True)
                        
                        # Final check
                        is_closed = await self._verify_dropdown_closed(dropdown_selectors)
                        if is_closed:
                            logger.debug("Dropdown closed after force click")
                    return True
            except Exception as e:
                        logger.debug(f"Force click failed: {e}")
                        
                    logger.warning("Dropdown remains open after multiple click attempts")
                    return False
                    
            except Exception as e:
                    logger.error(f"Error clicking option: {e}")
                    return False
                    
            else:
                similarity_info = ""
                if best_match:
                    try:
                        option_text = await best_match.text_content()
                        option_text = option_text.strip() if option_text else ""
                        similarity_info = f" (best match: '{option_text}' with score {best_score})"
                    except:
                        pass
                logger.warning(f"No suitable dropdown option found for '{value}'{similarity_info}")
            return False
            
        except Exception as e:
            logger.error(f"Error in _click_dropdown_option: {e}")
            return False
            
    async def _verify_dropdown_closed(self, dropdown_selectors, frame_id=None):
        """Verify that the dropdown is closed by checking if options are not visible."""
        try:
            # Wait a brief moment for animation to complete
            await asyncio.sleep(0.5)
            
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            
            # Check if dropdown options are still visible
            for selector in dropdown_selectors:
                try:
                    # Use a very short timeout since we expect this to fail if dropdown is closed
                    option_elements = await frame.query_selector_all(selector)
                    if option_elements and len(option_elements) > 0:
                        visible_count = 0
                        for option in option_elements:
                            is_visible = await self._is_element_visible(option, frame_id)
                            if is_visible:
                                visible_count += 1
                        
                        if visible_count > 0:
                            logger.debug(f"Dropdown appears to still be open: {visible_count} visible options")
                            return False
                except Exception:
                    # Exception is expected if selector is not found (dropdown closed)
                    pass
            
            logger.debug("Dropdown appears to be closed")
                return True
            
         except Exception as e:
            logger.debug(f"Error verifying dropdown closed: {e}")
            return True  # Assume closed on error

    def _calculate_basic_similarity(self, str1: str, str2: str) -> float:
        """Calculate basic string similarity when fuzzywuzzy is not available.

        Args:
            str1: First string to compare
            str2: Second string to compare

        Returns:
            Float between 0-100 representing similarity percentage
        """
        # Use Python's difflib SequenceMatcher for basic similarity
        similarity = SequenceMatcher(None, str1, str2).ratio()
        # Convert to percentage score similar to fuzzywuzzy (0-100)
        return similarity * 100

    async def get_field_value(
        self,
        selector: str,
        frame_id: Optional[str] = None
    ) -> str:
        """Get the current value of a field."""
        try:
        frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            element = await frame.query_selector(selector)
            if element:
                value = await element.input_value()
                return value
            return ""
        except Exception as e:
            self.logger.debug(f"Error getting field value: {e}")
            return ""

    async def set_checkbox(
        self,
        selector: str,
        checked: bool,
        frame_id: Optional[str] = None
    ) -> bool:
        """Set a checkbox to checked or unchecked."""
        try:
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            if checked:
                await frame.check(selector)
            else:
                await frame.uncheck(selector)
            self._log("debug", f"Set checkbox {selector} to {checked}")
            return True
        except Exception as e:
            self._log("error", f"Error setting checkbox {selector}: {e}")
            return False
    
    async def upload_file(
        self,
        selector: str,
        file_path: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Upload a file with graceful handling of missing files or test mode."""
        try:
            # Check if this is a resume or cover letter field (common patterns)
            is_resume = any(term in selector.lower() for term in ["resume", "cv"])
            is_cover = any(term in selector.lower() for term in ["cover", "letter"])
            
            # If file doesn't exist or we're skipping uploads
            if not os.path.exists(file_path) or not file_path:
                self._log("info", f"Skipping file upload for {selector} - path missing or in test mode")
                return True  # Return success to avoid breaking the workflow
                
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            if not frame:
                self._log("error", f"Frame not found for file upload: {frame_id}")
                return False
                
            element = await self.element_selector.find_element(selector, frame_id)
            if not element:
                self._log("error", f"Upload element not found: {selector}")
                return False
                
            # Set file input
            await element.set_input_files(file_path)
            self._log("info", f"Successfully uploaded file to {selector}")
            
            # Wait for upload to process
            await asyncio.sleep(1)
            
            return True
        except Exception as e:
            self._log("error", f"Error in upload_file for {selector}: {str(e)}")
            return False

    async def click_element(
        self,
        selector: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Click an element."""
        try:
            element = await self.element_selector.find_element(selector, frame_id)
            if element:
                await element.click()
                self._log("debug", f"Clicked element {selector}")
                return True
            else:
                frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
                if frame:
                        await frame.click(selector)
                    self._log("debug", f"Clicked element {selector} using frame.click")
                        return True
                else:
                    self._log("error", f"Failed to find element {selector} for clicking")
            return False
        except Exception as e:
            self._log("error", f"Error clicking element {selector}: {e}")
            return False

    async def handle_typeahead(
        self,
        selector: str,
        value: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Handle typeahead/autocomplete fields."""
        try:
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            element = await self.element_selector.find_element(selector, frame_id)
            
            if not element:
                self._log("error", f"Element not found: {selector}")
                return False
                
            # Clear and type value with some delay
            await element.fill("")
            await element.type(value, delay=50)
            await asyncio.sleep(POST_TYPE_DELAY)
            
            # First, try to wait for and select any appearing dropdown
            success = await self._try_select_from_dropdown(frame, value)
            if success:
                        return True
                    
            # If no dropdown or selection failed, press Enter to submit the value
            await element.press("Enter")
            await asyncio.sleep(POST_TYPE_DELAY)
            
            # Verify the value was accepted
            if await verify_input_value(frame, selector, value):
                    return True
                    
            # Final fallback: check if the current value is close enough
            current = await self.get_field_value(selector, frame_id)
            similarity = fuzz.ratio(current.lower(), value.lower()) / 100.0
            
            return similarity >= DEFAULT_FUZZY_THRESHOLD
            
        except Exception as e:
            self._log("error", f"Error in handle_typeahead for {selector}: {e}")
            return False
    
    async def _try_select_from_dropdown(self, frame, value: str) -> bool:
        """Try to select an option from a dropdown that may appear after typing."""
        try:
            # Common selectors for dropdown containers
            dropdown_selectors = [
                ".autocomplete-results", 
                ".dropdown-menu",
                ".combobox-options",
                "[role='listbox']"
            ]
            
            # Check if any dropdown is visible
            dropdown_visible = False
            for dropdown_selector in dropdown_selectors:
                try:
                    dropdown = await frame.query_selector(dropdown_selector)
                    if dropdown and await dropdown.is_visible():
                        dropdown_visible = True
                        break
                except Exception:
                    continue
            
            if not dropdown_visible:
            return False
            
            # Try to click a matching option
            return await self._click_dropdown_option(frame, value)
            
        except Exception as e:
            self.logger.debug(f"Error in _try_select_from_dropdown: {e}")
            return False
            
    async def type_and_select_option(self, selector, value, frame_id=None):
        """Type into a dropdown and select the best matching option."""
        try:
            # Get the appropriate frame
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            
            # Find and focus the input field
            element = await frame.wait_for_selector(selector, timeout=5000)
            if not element:
                logger.debug(f"Element not found: {selector}")
                self._log("error", f"Element not found: {selector}")
            return False
            
            # Clear and type value
            await element.fill("")
            await element.type(value, delay=100)
            await asyncio.sleep(0.75)
            
            # Try to find and click best option
            option_clicked = await self._click_dropdown_option(element, value)
            
            if option_clicked:
                if await verify_input_value(frame, selector, value, threshold=VERIFICATION_THRESHOLD):
                    return True
            return False
                
            # If clicking failed, try pressing Enter
            await element.press("Enter")
            await asyncio.sleep(0.5)
            
            return await verify_input_value(frame, selector, value, threshold=threshold)
            
        except Exception as e:
            self._log("error", f"Error in type_and_select_option: {e}")
            traceback.print_exc()
            return False

    async def clear_field(
        self,
        selector: str,
        frame_id: Optional[str] = None
    ) -> bool:
        """Clear the content of an input field."""
        try:
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            if frame:
                await frame.locator(selector).clear()
                self._log("debug", f"Cleared field: {selector}")
                return True
            return False
        except Exception as e:
            self._log("error", f"Error clearing field {selector}: {str(e)}")
            return False
                
    async def select_from_options(
        self, 
        selector: str,
        value: str,
        options: List[Union[str, Dict[str, str]]],
        frame_id: Optional[str] = None,
        threshold: float = HIGH_FUZZY_THRESHOLD
    ) -> bool:
        """Select an option from a list of pre-scraped options using fuzzy matching."""
        if not options:
            return False

        self._log("debug", f"Finding best match for '{value}' among {len(options)} options")
        
        # Extract and normalize options
        option_texts = []
        for option in options:
            if isinstance(option, str):
                option_texts.append(option.strip().lower())
            elif isinstance(option, dict):
                text = option.get('text', option.get('label', option.get('value', '')))
                if text:
                    option_texts.append(text.strip().lower())
        
        if not option_texts:
            return False
        
        # Find best match
        value_lower = value.strip().lower()
        matches = difflib.get_close_matches(value_lower, option_texts, n=1, cutoff=threshold)
        
        if not matches:
                return False
                
        best_match = matches[0]
        self._log("debug", f"Found match '{best_match}' for '{value}'")
        
        # After finding best match, attempt to select it using handle_typeahead
        return await self.handle_typeahead(selector, best_match, frame_id)
    
    async def _try_dismiss_dropdown(self, element, frame) -> None:
        """Dismiss any open dropdown."""
        try:
            if element:
                await element.press("Escape", timeout=1000)
            else:
                await frame.press("body", "Escape", timeout=1000)
            await asyncio.sleep(0.1)
        except Exception as e:
            self.logger.debug(f"Failed to dismiss dropdown: {e}")

    # Add this method for backward compatibility with TextActionHandler
    async def select_option_from_list(
        self,
        selector: str,
        value: str,
        available_options: List[Union[str, Dict[str, str]]],
        frame_id_str: Optional[str] = None,
        threshold: float = HIGH_FUZZY_THRESHOLD
    ) -> bool:
        """Alias for select_from_options to maintain backward compatibility."""
        return await self.select_from_options(selector, value, available_options, frame_id_str, threshold)

    async def type_and_select_fuzzy(
        self, 
        selector: str, 
        value: str, 
        frame_id_str: Optional[str] = None,
        threshold: float = DEFAULT_FUZZY_THRESHOLD
    ) -> bool:
        """Type text into a field and select the best fuzzy matching option from dropdown.
        
        Enhanced implementation with better dropdown detection, fuzzy matching,
        and more robust verification and fallback strategies.
        """
        try:
            # Get frame and element
            frame = await self.browser.get_frame(frame_id_str) if frame_id_str else self.browser.page
            if not frame:
                self._log("error", f"Failed to get frame object: {frame_id_str or 'main'}")
                return False

            element = await self.element_selector.find_element(selector, frame_id=frame_id_str)
            if not element:
                self._log("error", f"Element not found for selector: {selector} in frame: {frame_id_str or 'main'}")
                return False

            # Track success for verification
            selection_successful = False
            
            # Clear existing value and focus field
            await element.click()
            await asyncio.sleep(0.2)
            await element.fill("")
            
            # Try progressive typing to filter options as we type
            self._log("debug", f"Starting progressive typing for '{value}'")
            
            # First try typing the full value and wait for dropdown
            await element.type(value, delay=70)  # Slower typing for more reliable dropdown appearance
            await asyncio.sleep(0.8)  # Wait for dropdown to appear
            
            # Get visible dropdown options
            visible_options = await self._get_visible_dropdown_options(frame)
            self._log("debug", f"Found {len(visible_options)} visible options after typing")
            
            # Strategy 1: Find and click best matching option from visible options
            if visible_options:
                best_option, best_score = None, 0
                for option, option_element in visible_options:
                    similarity = self._calculate_similarity(option.lower(), value.lower())
                    if similarity > best_score and similarity >= threshold:
                        best_score = similarity
                        best_option = option_element
                
                if best_option:
                    self._log("debug", f"Clicking best match option with score {best_score:.2f}")
                    try:
                        await best_option.click()
                        await asyncio.sleep(0.3)
                        selection_successful = True
                    except Exception as e:
                        self._log("debug", f"Error clicking option: {e}")
            
            # Strategy 2: If no match found, try using arrow keys to navigate dropdown
            if not selection_successful:
                self._log("debug", f"Trying arrow key navigation")
                try:
                    # Ensure element is focused
                    await element.click()
                    await asyncio.sleep(0.2)
                    
                    # Try different key combinations
                    for key_sequence in [
                        ["ArrowDown", "Enter"],
                        ["ArrowDown", "ArrowDown", "Enter"],
                        ["Enter"],
                        ["Tab"]
                    ]:
                        for key in key_sequence:
                            await element.press(key)
                            await asyncio.sleep(0.2)
                        
                        # Check if selection successful
                        if await verify_selection(frame, selector, value, threshold=threshold):
                            selection_successful = True
                            break
                except Exception as e:
                    self._log("debug", f"Error in keyboard navigation: {e}")
            
            # Strategy 3: JavaScript approach - find and click option if previous methods failed
            if not selection_successful:
                self._log("debug", f"Trying JavaScript approach")
                
                # Use JavaScript to find options and click the best match
                js_result = await frame.evaluate("""
                    (value, threshold) => {
                        const normalize = text => text.toLowerCase().trim();
                        const valueNorm = normalize(value);
                        
                        // Find dropdown elements that might contain options
                        const containers = [
                            ...document.querySelectorAll('[role="listbox"], [class*="dropdown"], [class*="select"], [class*="menu"], [class*="results"], ul')
                        ].filter(el => el.offsetParent !== null); // Only visible elements
                        
                        if (!containers.length) return false;
                        
                        // Find all potential option elements
                        let options = [];
                        for (const container of containers) {
                            const containerOptions = [
                                ...container.querySelectorAll('[role="option"], li, div, *')
                            ].filter(el => el.offsetParent !== null);
                            
                            options.push(...containerOptions);
                        }
                        
                        // Find best matching option
                        let bestMatch = null;
                        let bestScore = 0;
                        
                            for (const option of options) {
                            const text = option.textContent || option.innerText || '';
                            if (!text.trim()) continue;
                            
                            // Simple text similarity check
                            const textNorm = normalize(text);
                            let score = 0;
                            
                            // Exact match
                            if (textNorm === valueNorm) {
                                score = 1.0;
                            } 
                            // Contains match
                            else if (textNorm.includes(valueNorm) || valueNorm.includes(textNorm)) {
                                score = 0.8;
                            }
                            // Word match
                            else {
                                const words1 = textNorm.split(/\\s+/);
                                const words2 = valueNorm.split(/\\s+/);
                                const common = words1.filter(w => words2.includes(w)).length;
                                if (common > 0) {
                                    score = common / Math.max(words1.length, words2.length);
                                }
                            }
                            
                            if (score > bestScore && score >= threshold) {
                                bestScore = score;
                                bestMatch = option;
                            }
                        }
                        
                        // Click the best match if found
                        if (bestMatch) {
                            bestMatch.click();
                            return true;
                        }
                        
                        return false;
                    }
                """, value, threshold)
                
                if js_result:
                    await asyncio.sleep(0.3)
                    selection_successful = True
            
            # Final verification
            if selection_successful or await verify_selection(frame, selector, value, threshold=threshold):
                self._log("debug", f"Successfully selected option for '{value}'")
                            return True
                
            # Always dismiss dropdown as cleanup
            await self._try_dismiss_dropdown(element, frame)
            
            # Return best-effort result
            return selection_successful
                    
                except Exception as e:
            self._log("error", f"Error in type_and_select_fuzzy: {e}")
            traceback.print_exc()
            
            # Cleanup: dismiss any open dropdown
            if 'frame' in locals() and 'element' in locals() and frame and element:
                await self._try_dismiss_dropdown(element, frame)
                
            return False
    
    async def _get_visible_dropdown_options(self, frame) -> List[Tuple[str, Any]]:
        """Get visible dropdown options as (text, element_handle) pairs."""
        options = []
        
        # Common dropdown option selectors
        option_selectors = [
            "[role=option]", 
            ".select__option", 
            "[class*='option']", 
            "[class*='dropdown'] li", 
            "[class*='select'] div", 
            "[class*='autocomplete'] div",
            "[class*='menu'] div",
            ".results li",
            "ul li"
        ]
        
        for selector in option_selectors:
            try:
                elements = await frame.query_selector_all(selector)
                for element in elements:
                    if not await element.is_visible():
                        continue
                        
                    text = await element.text_content()
                    if text and text.strip():
                        options.append((text.strip(), element))
            except Exception:
                continue
                
        return options

    async def retry_failed_actions(
        self,
        failed_actions: List[Dict[str, Any]],
        max_retries: int = 2
    ) -> Dict[str, Tuple[bool, str]]:
        """Retry failed form actions with alternative strategies.
        
        Args:
            failed_actions: List of action dictionaries that failed
            max_retries: Maximum number of retry attempts per action
            
        Returns:
            Dictionary mapping field_id to (success, message) tuples
        """
        results = {}
        
        for action in failed_actions:
            field_id = action.get("field_id")
            value = action.get("value")
            selector = action.get("selector") 
            frame_id = action.get("frame_id")
            field_type = action.get("field_type", "text")
            
            if not field_id or not selector:
                continue
                
            self._log("info", f"Retrying failed action for {field_id} with type {field_type}")
            
            # Skip file uploads in retry logic
            if field_type == "file":
                results[field_id] = (True, "Skipped file upload during retry")
                continue
                
            success = False
            error_message = "Failed all retry attempts"
            
            for attempt in range(max_retries):
                try:
                    self._log("debug", f"Retry attempt {attempt+1}/{max_retries} for {field_id}")
                    
                    # Use different strategies based on attempt number and field type
                    if field_type in ["text", "select", "combobox", "autocomplete"]:
                        if attempt == 0:
                            # First try: Use more direct approach - clear, type and immediately press Enter
                            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
                            element = await self.element_selector.find_element(selector, frame_id)
                            
        if element:
                                await element.click()
                                await asyncio.sleep(0.2)
                                await element.fill("")
                                await element.type(value, delay=50)
                                await element.press("Enter")
                                await asyncio.sleep(0.3)
                                success = await verify_input_value(frame, selector, value, threshold=0.7)
                        elif attempt == 1:
                            # Second try: Use keyboard navigation
                            success = await self._retry_with_keyboard_nav(selector, value, frame_id)
                    elif field_type in ["checkbox", "radio"]:
                        # For checkboxes, just try clicking
                        success = await self.click_element(selector, frame_id)
                    elif field_type == "button":
                        # For buttons, try different click methods
                        success = await self._retry_button_click(selector, frame_id)
                        
                    if success:
                        error_message = f"Success on retry attempt {attempt+1}"
                        break
                        
                    # Pause between attempts
                    await asyncio.sleep(1.0)
                    
                except Exception as e:
                    error_message = f"Error during retry: {str(e)}"
                    self._log("error", error_message)
            
            results[field_id] = (success, error_message)
            
        return results
        
    async def _retry_with_keyboard_nav(self, selector: str, value: str, frame_id: Optional[str] = None) -> bool:
        """Try to fill a field using keyboard navigation."""
        try:
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            element = await self.element_selector.find_element(selector, frame_id)
            
            if not element:
                return False

            # Focus and clear
            await element.click()
            await asyncio.sleep(0.2)
            await element.fill("")
            
            # Type value character by character with delay
            for char in value:
                await element.type(char, delay=30)
                await asyncio.sleep(0.1)
            
            # Try different keyboard combinations
            for key_combo in ["Enter", "Tab", "ArrowDown Enter", "ArrowDown ArrowDown Enter"]:
                for key in key_combo.split():
                    await element.press(key)
                    await asyncio.sleep(0.3)
                
                if await verify_input_value(frame, selector, value, threshold=0.7):
                    return True
                    
                return False

        except Exception as e:
            self._log("error", f"Error in keyboard navigation retry: {e}")
            return False
    
    async def _retry_button_click(self, selector: str, frame_id: Optional[str] = None) -> bool:
        """Try different methods to click a button that failed."""
        try:
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            
            # Try direct click
            try:
                await frame.click(selector, timeout=2000)
                        return True
                except Exception:
                pass
                
            # Try JavaScript click
            try:
                element_handle = await frame.query_selector(selector)
                if element_handle:
                    await frame.evaluate("(element) => element.click()", element_handle)
                    return True
            except Exception:
                pass
                
            # Try Enter key on element
            try:
                element = await self.element_selector.find_element(selector, frame_id)
                if element:
                    await element.press("Enter")
                return True
            except Exception:
                pass
                
                return False
            
        except Exception as e:
            self._log("error", f"Error in button click retry: {e}")
            return False
            
    def type_and_select_option_fuzzy(self, selector, value, frame_id_str=None):
        """An alias for type_and_select_fuzzy for backward compatibility.
        
        This method exists to maintain compatibility with code that calls this method directly.
        """
        return self.type_and_select_fuzzy(selector, value, frame_id_str)

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate string similarity using fuzzywuzzy if available or basic similarity if not.
        
        Args:
            str1: First string to compare
            str2: Second string to compare
            
        Returns:
            Float between 0-100 representing similarity percentage
        """
        try:
            return fuzz.token_sort_ratio(str1, str2)
        except (ImportError, NameError):
            return self._calculate_basic_similarity(str1, str2)

    async def _find_dropdown_options(self, dropdown_selectors, frame_id=None):
        """Find visible dropdown option elements in the page."""
        options = []
        
        if dropdown_selectors:
            try:
                for selector in dropdown_selectors:
                    try:
                        # Wait briefly for options to appear
                        frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
                        await frame.wait_for_selector(selector, timeout=1000)
                        option_elements = await frame.query_selector_all(selector)
                        if option_elements:
                            options.extend(option_elements)
                            break
                except Exception as e:
                        logger.debug(f"Error finding options with selector {selector}: {e}")
        except Exception as e:
                logger.debug(f"Error finding dropdown options: {e}")
                
        return options

    async def _verify_selection(self, element, value, frame_id=None):
        """Verify if the selected value is correct by checking the field value."""
        try:
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            # Get the current value of the field
            current_value = await frame.evaluate("""el => {
                return el.value || el.textContent || '';
            }""", element)
            
            # Normalize both values for comparison
            current_value = current_value.strip().lower()
            expected_value = value.strip().lower()
            
            # Check if the values match or if expected value is contained in current value
            if current_value == expected_value or expected_value in current_value:
                logger.debug(f"Verification successful: Current value '{current_value}' matches expected '{expected_value}'")
                    return True
                
            logger.debug(f"Verification failed: Current value '{current_value}' does not match expected '{expected_value}'")
            return False

        except Exception as e:
            logger.debug(f"Error verifying selection: {e}")
            return False

    async def _find_best_matching_option(self, options, value, threshold=70, frame_id=None):
        """Find the best matching option element based on text similarity."""
        best_match = None
        best_score = 0
        frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
        
        try:
            # Get visible options with their text content
            visible_options = []
            for option in options:
                try:
                    is_visible = await self._is_element_visible(option, frame_id)
                    if is_visible:
                        # Get option text
                        option_text = await frame.evaluate("""el => {
                            return el.textContent || el.innerText || el.value || '';
                        }""", option)
                        
                        if option_text:
                            option_text = option_text.strip()
                            visible_options.append((option_text, option))
                except Exception as e:
                    logger.debug(f"Error getting option text: {e}")
            
            logger.debug(f"Found {len(visible_options)} visible options")
            
            # Find best matching option
            for option, option_element in visible_options:
                similarity = self._calculate_similarity(option.lower(), value.lower())
                if similarity > best_score and similarity >= threshold:
                    best_score = similarity
                    best_match = option_element
                    logger.debug(f"Found better match: '{option}' with score {similarity}")
            
            if best_match:
                logger.debug(f"Best match found with score {best_score}")
                 else:
                logger.debug(f"No match found above threshold {threshold}")

        except Exception as e:
            logger.debug(f"Error finding best matching option: {e}")
            
        return best_match, best_score

    async def _is_element_visible(self, element, frame_id=None):
        """Check if an element is visible in the current frame."""
            try:
                frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            is_visible = await frame.evaluate("""el => {
                const style = window.getComputedStyle(el);
                return style.display !== 'none' &&
                       style.visibility !== 'hidden' &&
                       style.opacity !== '0' &&
                       el.offsetWidth > 0 &&
                       el.offsetHeight > 0;
            }""", element)
            return is_visible
            except Exception as e:
            logger.debug(f"Error checking element visibility: {e}")
            return False

    async def set_dropdown(self, selector, value, use_keyboard=True, frame_id=None):
        """Select a value from a dropdown field."""
        if not value:
            logger.debug(f"No value provided for dropdown {selector}")
            return False

        try:
            # Get the appropriate frame
            frame = await self.browser.get_frame(frame_id) if frame_id else self.browser.page
            
            # Wait for and focus on the dropdown element
            element = await frame.wait_for_selector(selector, timeout=5000)
            if not element:
                logger.debug(f"Dropdown element not found: {selector}")
            return False

            if use_keyboard:
                # Use keyboard to select the value
                await self.type_and_select_option(selector, value, frame_id)
        else:
                # Use mouse to select the value
                await self.select_option(selector, value, None, frame_id)

            return True
        except Exception as e:
            logger.error(f"Error setting dropdown: {e}")
            return False