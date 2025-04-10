"""Handles actions for standard <select> elements and custom dropdowns."""

import logging
import asyncio
from typing import Optional, List, Dict, Any # Added Dict, List, Any
from playwright.async_api import Frame # Added Frame import

from .base_handler import BaseActionHandler
from enterprise_job_agent.core.exceptions import ActionExecutionError, ElementNotFoundError
# Import strategy selector
from ..action_strategy_selector import ActionStrategySelector 
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager # Import DiagnosticsManager

class SelectActionHandler(BaseActionHandler):
    """Handles actions for both standard <select> and custom dropdown widgets."""
    
    def __init__(self, browser_manager, form_interaction, element_selector, diagnostics_manager, strategy_selector: ActionStrategySelector):
        """Initialize the handler with necessary components."""
        # Pass expected arguments to BaseActionHandler
        super().__init__(browser_manager, form_interaction, element_selector)
        self.strategy_selector = strategy_selector # Store strategy selector
        self.diagnostics_manager = diagnostics_manager # Store diagnostics manager
        self.logger = logging.getLogger(__name__) # Use standard logger
        if not self.strategy_selector:
             self.logger.warning("ActionStrategySelector not provided to SelectActionHandler. Interactions may be suboptimal.")

    async def execute(self, context) -> bool:
        """Executes a selection action based on the identified widget type using strategies."""
        selector = context.field_id
        value = context.field_value
        frame_id = context.frame_id
        element_data = context.options.get("element_data") if context.options else None
        widget_type = element_data.get("widget_type", "unknown") if element_data else "unknown"

        if not selector or not value:
            self.logger.error(f"Missing selector ('{selector}') or value ('{value}') for select action.")
            return False

        self.logger.info(f"Executing select action for '{selector}' with value '{value}' (widget: {widget_type})")

        try:
            frame = await self._get_frame(frame_id)
            safe_selector = await self._sanitize_selector(selector)
            # Ensure the main trigger/element is available before proceeding
            await self._ensure_element_visibility(frame, safe_selector) 

            # Choose primary path based on widget type
            if widget_type == "standard_select":
                return await self._handle_standard_select_with_strategy(frame, safe_selector, value, element_data)
            elif widget_type in ["custom_select", "autocomplete"]: # Group custom/autocomplete
                 return await self._handle_custom_select_with_strategy(frame, safe_selector, value, element_data)
            else:
                 self.logger.warning(f"Unsupported widget_type '{widget_type}' for selector '{safe_selector}'. Attempting standard select strategy as fallback.")
                 # Fallback to standard select logic if widget type is unknown or unexpected
                 return await self._handle_standard_select_with_strategy(frame, safe_selector, value, element_data)
                 
        except ActionExecutionError as ae:
            self.logger.error(f"ActionExecutionError during select action for {selector}: {ae}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during select action for {selector}: {e}", exc_info=True)
            raise ActionExecutionError(f"Failed to execute select action for '{selector}'") from e
            
    # --- Strategy-Driven Handlers --- 
    
    async def _handle_standard_select_with_strategy(self, frame, selector, value, element_data) -> bool:
        """Handles standard <select> elements using a strategy chosen by the LLM."""
        self.logger.debug(f"Handling standard select for {selector} with strategy selection")
        strategy = "select_option_by_label" # Default
        if self.strategy_selector and element_data:
            strategy = await self.strategy_selector.select_strategy(element_data, value)
            strategy = strategy if strategy in ["select_option_by_label", "select_option_by_value", "select_option_by_fuzzy_match"] else "select_option_by_label"
        else:
             log_reason = "element_data missing" if not element_data else "StrategySelector missing"
             self.logger.warning(f"Skipping strategy selection for standard select ({log_reason}).")
             
        self.logger.info(f"Using strategy '{strategy}' for standard select {selector}")

        # Extract options directly from element_data if available (passed from FormAnalyzerAgent)
        options_from_analysis = element_data.get("options") if element_data else None
        
        # Map strategy to action
        if strategy == "select_option_by_label":
             # Try exact label match first
             success = await self.form_interaction.select_option(frame, selector, label=value)
             if success: return True
             # Fallback to fuzzy label match if exact fails
             self.logger.debug("Exact label match failed for standard select, trying semantic match...")
             return await self._select_option_semantic_match(frame, selector, value, options_from_analysis, element_data)
        elif strategy == "select_option_by_value":
             # Note: Requires `value` to be the actual 'value' attribute. 
             # Assumes ProfileAdapter or FormAnalyzer provides this context correctly.
             return await self.form_interaction.select_option(frame, selector, value=value)
        elif strategy == "select_option_by_fuzzy_match":
            self.logger.debug("Executing semantic match strategy for standard select.")
            return await self._select_option_semantic_match(frame, selector, value, options_from_analysis, element_data)
        else:
             # Should not happen due to fallback logic above, but handle defensively
             self.logger.warning(f"Unknown or invalid strategy '{strategy}' for standard select. Falling back to semantic match.")
             return await self._select_option_semantic_match(frame, selector, value, options_from_analysis, element_data)
             
    async def _handle_custom_select_with_strategy(self, frame, selector, value, element_data) -> bool:
        """Handles custom dropdowns/autocompletes using a strategy chosen by the LLM."""
        widget_type = element_data.get("widget_type", "custom_select") if element_data else "custom_select"
        self.logger.debug(f"Handling {widget_type} for {selector} with strategy selection")
        
        # Determine default strategy based on widget type
        default_strategy = "type_and_select_fuzzy" if widget_type == "autocomplete" else "click_and_select_fuzzy"
        
        strategy = default_strategy 
        possible_strategies = self.strategy_selector._get_possible_strategies(widget_type) if self.strategy_selector else [default_strategy]
        
        if self.strategy_selector and element_data:
            strategy = await self.strategy_selector.select_strategy(element_data, value)
            strategy = strategy if strategy in possible_strategies else default_strategy
        else:
             log_reason = "element_data missing" if not element_data else "StrategySelector missing"
             self.logger.warning(f"Skipping strategy selection for {widget_type} ({log_reason}).")
             
        self.logger.info(f"Using strategy '{strategy}' for {widget_type} {selector}")
        
        field_type = element_data.get("field_type") if element_data else None
        
        # Map strategy to action
        # Note: These map to different parameter combinations of the same core interaction logic method
        if strategy == "click_and_select_exact":
             return await self._custom_select_interaction(frame, selector, value, field_type, type_first=False, exact_match=True)
        elif strategy == "click_and_select_fuzzy":
             return await self._custom_select_interaction(frame, selector, value, field_type, type_first=False, exact_match=False)
        elif strategy == "type_and_select_exact":
             return await self._custom_select_interaction(frame, selector, value, field_type, type_first=True, exact_match=True)
        elif strategy == "type_and_select_fuzzy":
             return await self._custom_select_interaction(frame, selector, value, field_type, type_first=True, exact_match=False)
        elif strategy == "fill_and_confirm": # Primarily for autocomplete where selection might not be needed
             self.logger.info("Using 'fill_and_confirm' strategy: filling field and assuming confirmation (e.g., blur) handles it.")
             success = await self.form_interaction.fill_field(frame, selector, value)
             if success:
                 await asyncio.sleep(0.5) # Allow time for potential background actions
                 # Consider adding a blur action here if needed: await frame.locator(selector).blur()
             return success
        elif strategy == "clear_and_type_and_select": # For autocompletes needing clear first
             self.logger.info("Using 'clear_and_type_and_select' strategy.")
             if await self.form_interaction.clear_field(frame, selector):
                 return await self._custom_select_interaction(frame, selector, value, field_type, type_first=True, exact_match=False) # Default to fuzzy after clear+type
             else:
                  self.logger.warning(f"Failed to clear field {selector} for clear_and_type_and_select strategy.")
                  return False
        else:
            # Should not happen due to fallback, but handle defensively
            self.logger.warning(f"Unknown or invalid strategy '{strategy}' for {widget_type}. Falling back to default: '{default_strategy}'.")
            if default_strategy.startswith("type_"):
                 return await self._custom_select_interaction(frame, selector, value, field_type, type_first=True, exact_match=False)
            else:
                 return await self._custom_select_interaction(frame, selector, value, field_type, type_first=False, exact_match=False)
            
    # --- Helper Methods for Strategies --- 
    
    async def _select_option_semantic_match(self, frame, selector, value, options_from_analysis: Optional[List[Dict]], element_data: Optional[Dict[str, Any]]) -> bool:
        """Uses the LLM via ActionStrategySelector to find and select the best semantic match in a standard select."""
        self.logger.debug(f"Attempting semantic match for standard select {selector} with value '{value}'")
        
        option_texts = []
        if options_from_analysis:
             option_texts = [opt.get('text', '') for opt in options_from_analysis if opt.get('text')] # Extract non-empty text
        
        if not option_texts:
             self.logger.warning(f"Cannot perform semantic match for {selector}: Options not available from analysis or empty.")
             # Optional: Could try scraping options here as a fallback using form_interaction
             # try:
             #      options = await self.form_interaction.get_select_options(frame, selector)
             #      option_texts = [opt['label'] for opt in options]
             # except Exception as scrape_err:
             #      self.logger.error(f"Failed to scrape options for fallback semantic match on {selector}: {scrape_err}")
             #      return False
             return False # Fail if no options are available
             
        # Use LLM for semantic matching
        best_match_text = None
        if self.strategy_selector:
            # Add logging for semantic match input/output
            self.logger.debug(f"Calling semantic match for standard select: desired='{value}', options={option_texts[:10]}...")
            best_match_text = await self.strategy_selector.find_best_match_semantic(value, option_texts, element_data)
        else:
            self.logger.warning("StrategySelector not available, cannot perform semantic match.")
        
        if best_match_text:
            self.logger.info(f"LLM semantic match found: '{best_match_text}'. Attempting selection by label.")
            # Select using the matched text (label)
            selection_attempted = await self.form_interaction.select_option(frame, selector, label=best_match_text)
            if selection_attempted:
                 # Verify the selection
                 self.logger.info(f"Selection attempt successful for '{best_match_text}', verifying...")
                 return await self._verify_selection(frame, selector, best_match_text, is_standard_select=True)
            else:
                 self.logger.error(f"Form interaction failed to select label '{best_match_text}' for {selector}.")
                 return False
        else:
            self.logger.warning(f"No suitable semantic match found by LLM for '{value}' in standard select {selector}")
            return False
            
    async def _custom_select_interaction(self, frame, selector, value, field_type, type_first=False, exact_match=False) -> bool:
        """Core logic for interacting with custom dropdowns (click/type, scrape, match, select)."""
        self.logger.debug(f"Custom select interaction: selector={selector}, value={value}, type_first={type_first}, exact_match={exact_match}")
        
        # 1. Initial Interaction (Click or Type)
        if type_first:
            self.logger.debug(f"Typing '{value}' into custom select/autocomplete {selector}")
            # Use fill_field, assuming it triggers filtering/suggestions
            if not await self.form_interaction.fill_field(frame, selector, value):
                self.logger.warning(f"Failed to type into custom select/autocomplete {selector}")
                # Fallback: Try clicking first if typing fails? Or just fail?
                # Let's fail for now, assuming typing is the intended primary action for this strategy.
                return False
            # Wait for options to filter/appear after typing
            await asyncio.sleep(0.7) # Slightly longer wait after typing
        else:
            self.logger.debug(f"Clicking custom select {selector} to open options")
            if not await self.form_interaction.click_element(frame, selector):
                 self.logger.error(f"Failed to click custom select trigger: {selector}")
                 return False
            # Wait for options to appear after click
            await asyncio.sleep(0.5) 

        # 2. Scrape Options
        # Use the dedicated scraping method
        scraped_options = await self._scrape_options_from_dropdown(frame, selector)
        if not scraped_options:
            self.logger.warning(f"Could not scrape options for custom select {selector} after interaction.")
            # Attempt to close dropdown (best effort) before failing
            await self._try_close_dropdown(frame)
            return False 
            
        option_texts = [opt['text'] for opt in scraped_options if opt.get('text')] # Ensure text exists
        if not option_texts:
             self.logger.warning(f"Scraped options for {selector} but found no text content.")
             await self._try_close_dropdown(frame)
             return False
             
        self.logger.debug(f"Scraped {len(option_texts)} options: {option_texts[:10]}...")
        
        # 3. Find Match
        target_option_text = None
        if exact_match:
             # Look for exact text match (case-insensitive)
             for text in option_texts:
                 if value.lower() == text.lower():
                      target_option_text = text
                      self.logger.info(f"Found exact match in custom dropdown options: '{target_option_text}'")
                      break
        
        if not target_option_text: # If exact match requested but failed, or if fuzzy match needed
            if exact_match:
                 self.logger.warning(f"Exact match requested but not found for '{value}' in custom select options.")
                 # Fail if exact match was specifically requested and not found.
                 await self._try_close_dropdown(frame)
                 return False
                 
            # Use DropdownMatcher for fuzzy matching
            self.logger.debug("Performing semantic match for custom select options...")
            element_context = await self.element_selector.get_element_details(selector, frame)
            
            # Generate variants using the static method from ActionStrategySelector
            value_variants = ActionStrategySelector.generate_text_variants(value, field_type)
            
            best_match_text = None
            if self.strategy_selector:
                best_match_text = await self.strategy_selector.find_best_match_semantic(
                    desired_value=value,
                    options=option_texts,
                    element_context=element_context,
                    value_variants=value_variants # Pass variants
                )
            else:
                # Raise an error if strategy_selector is None, as it should always be provided
                self.logger.error("ActionStrategySelector is not initialized but is required for semantic matching.")
                raise ValueError("ActionStrategySelector is required for semantic matching but was not provided.")

            if best_match_text:
                target_option_text = best_match_text
                self.logger.info(f"Found LLM semantic match in custom dropdown options: '{target_option_text}'")
            else:
                self.logger.warning(f"No suitable semantic match found by LLM for '{value}' in custom select options {selector}")
                await self._try_close_dropdown(frame)
                return False

        # 4. Select Matched Option
        self.logger.debug(f"Attempting to click the matched option: '{target_option_text}'")
        # Revised flow: _find_and_click_option_by_text attempts click and returns success bool
        clicked_option = await self._find_and_click_option_by_text(frame, target_option_text)

        if clicked_option:
             self.logger.info(f"Successfully selected '{target_option_text}' in custom select/autocomplete {selector}")
             await asyncio.sleep(0.5) # Brief pause after selection
             # Selection usually closes the dropdown, no explicit close needed normally.
             # Verify the selection (check the input field's value)
             self.logger.info(f"Selection attempt successful for '{target_option_text}', verifying...")
             return await self._verify_selection(frame, selector, target_option_text, is_standard_select=False)
        else:
             self.logger.error(f"Failed to find or click the matched option: {target_option_text}")
             # Attempt to close dropdown (best effort) before failing
             await self._try_close_dropdown(frame)
             return False

    # --- Verification Helper ---

    async def _verify_selection(self, frame: Frame, selector: str, expected_value: str, is_standard_select: bool) -> bool:
        """Verify if the selected value in the dropdown/input matches the expected value."""
        await asyncio.sleep(0.5) # Wait for UI to potentially update
        self.logger.debug(f"Verifying selection for {selector}. Expected: '{expected_value}'")
        actual_value = None
        try:
            element = frame.locator(selector).first
            if not element:
                 self.logger.error(f"Verification failed: Element {selector} not found.")
                 return False

            if is_standard_select:
                # For standard <select>, check the value of the selected <option>
                # Playwright's select_option handles this internally, but we verify the input value attribute if possible,
                # or check the selected option's text as a fallback.
                try:
                     # Check the <select> element's value attribute first
                     actual_value = await element.input_value()
                     self.logger.debug(f"Verification using <select> input_value(): '{actual_value}'")
                except Exception:
                     # Fallback: find the selected option and get its text
                     try:
                          selected_option = await element.locator("option:checked").first
                          if selected_option:
                               actual_value = await selected_option.text_content()
                               self.logger.debug(f"Verification using selected option text: '{actual_value}'")
                          else:
                               self.logger.warning(f"Could not find checked option for {selector} during verification.")
                     except Exception as e:
                          self.logger.warning(f"Error getting selected option text for {selector}: {e}")

            else: # For custom dropdowns/typeaheads, check the input field's value
                try:
                    actual_value = await element.input_value()
                    self.logger.debug(f"Verification using <input> input_value(): '{actual_value}'")
                except Exception as e:
                    # Some custom inputs might not support input_value(), try text_content as fallback
                    self.logger.warning(f"Failed to get input_value for {selector} during verification ({e}), trying text_content.")
                    try:
                         actual_value = await element.text_content()
                         self.logger.debug(f"Verification using element text_content(): '{actual_value}'")
                    except Exception as e2:
                         self.logger.error(f"Verification failed: Could not get input_value or text_content for {selector}: {e2}")
                         return False

            if actual_value is None:
                 self.logger.warning(f"Verification failed: Could not retrieve actual value for {selector}.")
                 return False

            # Normalize both values for comparison
            norm_expected = ActionStrategySelector.normalize_text(expected_value)
            norm_actual = ActionStrategySelector.normalize_text(actual_value)
            similarity = self.strategy_selector.calculate_similarity(norm_expected, norm_actual) if self.strategy_selector else 0.0

            # Use a high threshold for verification
            verification_threshold = 0.90 
            if similarity >= verification_threshold:
                self.logger.info(f"Verification SUCCESS for {selector}. Expected: '{expected_value}', Got: '{actual_value}' (Similarity: {similarity:.2f})")
                return True
            else:
                self.logger.warning(f"Verification FAILED for {selector}. Expected: '{expected_value}', Got: '{actual_value}' (Similarity: {similarity:.2f} < {verification_threshold})")
                return False

        except Exception as e:
            self.logger.error(f"Error during verification for {selector}: {e}", exc_info=True)
            return False # Fail verification on any unexpected error

    # --- Existing Helper Methods (potentially refactored/reused) ---
    # These helpers support the strategy execution

    async def _scrape_options_from_dropdown(self, frame, trigger_selector) -> List[Dict[str, str]]:
        """Attempts to scrape options currently visible in a dropdown list.
           Assumes dropdown was potentially opened by a previous interaction.
        """
        options = set()
        # Common selectors for options within dropdown menus/lists
        option_selectors = [
            "[role='option']",
            "li[role='option']",
            "div[role='option']",
            ".dropdown-item",
            ".select-option",
            ".lookup__list__item",
            ".menu-item",
            "ul[role='listbox'] li", # Listbox items
            "div[class*='option']", # Classes containing 'option'
            "li[class*='item']" # Classes containing 'item'
        ]
        try:
             # Wait briefly for options to render after potential click
             await asyncio.sleep(0.4) # Slightly longer wait

             # Try finding options relative to the trigger or globally
             possible_containers = [
                 frame.locator(trigger_selector).locator('xpath=ancestor::div[contains(@class, "dropdown")] | ancestor::div[ul or ol]').first, # Ancestor dropdown container
                 frame # Global search as fallback
             ]

             found_in_container = False
             for container in possible_containers:
                 if found_in_container: break
                 for opt_selector in option_selectors:
                     try:
                         # Find elements within the container or globally
                         elements = await container.locator(opt_selector).all()
                         if elements:
                             count = 0
                             for el in elements:
                                 try:
                                     # Check visibility robustly
                                     if await el.is_visible(timeout=200): # Short timeout per element
                                         text = await el.text_content()
                                         if text and text.strip() and len(text.strip()) > 1:
                                             options.add(text.strip())
                                             count += 1
                                 except Exception: # Ignore errors for individual elements
                                     continue
                             if count > 0:
                                 self.logger.debug(f"Found {count} visible options with selector '{opt_selector}' within container/frame.")
                                 found_in_container = True # Stop searching other selectors if options found
                                 # break # Optionally break inner loop once options are found with one selector

                     except Exception as e:
                         # Log query errors but continue trying other selectors/containers
                         self.logger.debug(f"Error querying options with {opt_selector}: {e}")

             if options:
                  self.logger.info(f"Scraped {len(options)} unique visible options potentially related to {trigger_selector}")
             else:
                  self.logger.warning(f"Could not scrape any visible options for {trigger_selector}")

        except Exception as e:
             self.logger.error(f"Error scraping dropdown options for {trigger_selector}: {e}")

        return list(options)

    async def _try_close_dropdown(self, frame: Frame):
        """Attempts to dismiss an open dropdown, usually by pressing Escape."""
        try:
            page = self.browser_manager.get_page()
            if page:
                 await page.keyboard.press("Escape")
                 self.logger.debug("Pressed Escape key to dismiss dropdown.")
                 await asyncio.sleep(0.2) # Short pause
                 return
            # Fallback: Click body - less reliable, avoid if possible
            # self.logger.debug("Attempting to click body to dismiss dropdown (fallback).")
            # await frame.locator('body').click(timeout=1000, force=True)
        except Exception as e:
            self.logger.warning(f"Could not dismiss dropdown via Escape/Click: {e}")

    async def _find_and_click_option_by_text(self, frame: Frame, text: str) -> bool:
        """Finds a selector for an element containing the given text and clicks it. Returns True if clicked, False otherwise."""
        # (This combines logic from the old _find_option_selector_by_text and the click action)
        self.logger.debug(f"Finding and clicking option with text: '{text}'")
        escaped_text = text.replace("'", "\\'").replace("\"", '\\"')

        selectors_to_try = [
            f"[role='option']:has-text('{escaped_text}')",
            f"li:has-text('{escaped_text}')",
            f"div[role='option']:has-text('{escaped_text}')", # Added specific div role
            f".dropdown-item:has-text('{escaped_text}')",
            f".menu-item:has-text('{escaped_text}')",
            f".select-option:has-text('{escaped_text}')",
            f"span:has-text('{escaped_text}')",
             # Trying exact text match selectors as well
             f"[role='option']:text-is('{escaped_text}')",
             f"li:text-is('{escaped_text}')",
             f"div:text-is('{escaped_text}')", # General div with exact text
        ]

        for selector in selectors_to_try:
            try:
                elements = await frame.locator(selector).all()
                if not elements: continue

                self.logger.debug(f"Found {len(elements)} potential elements for text '{text}' with selector '{selector}'")
                for element in elements:
                    try:
                        # Ensure element is visible before clicking
                        await element.wait_for(state='visible', timeout=1500) # Increased timeout slightly
                        await element.click(timeout=3000)
                        self.logger.info(f"Successfully clicked option '{text}' using selector: {selector}")
                        return True # Click succeeded
                    except Exception as click_err:
                        self.logger.debug(f"Element found with {selector} but click failed or not visible/interactable: {click_err}")
                        continue # Try next element matching this selector

            except Exception as query_err:
                self.logger.debug(f"Error querying or interacting with selector {selector}: {query_err}")

        # Fallback: Use Playwright's general text selector (less preferred)
        try:
            self.logger.debug(f"Trying general text selector for: '{escaped_text}'")
            # Prioritize elements likely to be options
            general_locator = frame.locator(f"button:text-is('{escaped_text}'), a:text-is('{escaped_text}'), [role='option']:text-is('{escaped_text}'), li:text-is('{escaped_text}'), div:text-is('{escaped_text}')")
            count = await general_locator.count()
            if count > 0:
                 self.logger.debug(f"Found {count} elements with general text-is selector.")
                 for i in range(count):
                     el = general_locator.nth(i)
                     try:
                          await el.wait_for(state='visible', timeout=1000)
                          await el.click(timeout=3000)
                          self.logger.info(f"Successfully clicked option '{text}' using general text-is selector.")
                          return True
                     except Exception:
                          continue 
        except Exception as e:
             self.logger.debug(f"General text selector failed for '{text}': {e}")
             
        self.logger.warning(f"Could not find and click a visible option matching text '{text}'")
        return False # Failed to find and click

# Remove the old verification logic at the end of the file if it exists
# # --- Verification logic (Example - Requires refinement) ---
# # async def _verify_selection(self, frame: Frame, selector: str, expected_value: str) -> bool:
# # ... (delete this commented out block) ...
# #         return False # Fail verification on error 