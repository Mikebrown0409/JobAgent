"""Handles typeahead/autocomplete actions, including specialized location handling."""
import logging
import asyncio
import re
from typing import List, Optional
from playwright.async_api import Frame, Page, Error as PlaywrightError

from .base_handler import BaseActionHandler
from enterprise_job_agent.core.exceptions import ActionExecutionError, ElementNotFoundError
# REMOVE DropdownMatcher import
# from enterprise_job_agent.tools.dropdown_matcher import DropdownMatcher
from .select_handler import SelectActionHandler # Keep this for helpers
from ..action_strategy_selector import ActionStrategySelector

class TypeaheadActionHandler(BaseActionHandler):
    """Handles interactions with typeahead/autocomplete fields."""
    
    def __init__(self, browser_manager, form_interaction, element_selector, diagnostics_manager, strategy_selector: ActionStrategySelector, logger=None):
        """Initialize the handler with necessary components."""
        super().__init__(browser_manager, form_interaction, element_selector)
        self.strategy_selector = strategy_selector
        self.diagnostics_manager = diagnostics_manager
        
        # Instantiate SelectActionHandler helper - REMOVED dropdown_matcher argument
        self.select_helper = SelectActionHandler(
            browser_manager=self.browser_manager,
            form_interaction=self.form_interaction,
            element_selector=self.element_selector,
            diagnostics_manager=self.diagnostics_manager,
            # dropdown_matcher=... # Removed
            strategy_selector=self.strategy_selector
        )
        if not self.strategy_selector:
            self.logger.warning("ActionStrategySelector not provided to TypeaheadActionHandler.")

    async def execute(self, context) -> bool:
        """Executes a typeahead action, potentially using specialized location logic."""
        field_id = context.field_id
        field_value = context.field_value
        frame_id = context.frame_id
        element_data = context.options.get("element_data") if context.options else None
        # Get field_type directly from element_data or default
        field_type = element_data.get("field_type", "typeahead") if element_data else "typeahead"
        
        # Remove call to non-existent _infer_field_type_basic
        # field_name = context.options.get('name') if context.options else None
        # if not field_type and field_id:
        #     field_type = self.select_helper._infer_field_type_basic(field_id) # REMOVED
             
        log_target = f"selector '{field_id}' with value '{field_value}' (type: {field_type or 'typeahead'})"
        self.logger.debug(f"Executing typeahead action for {log_target}")

        if not field_id or field_value is None:
            self.logger.error(f"Missing field_id ('{field_id}') or value ('{field_value}') for typeahead action.")
            return False

        try:
            # Decide based on field type - special handling for locations
            # TODO: Improve location field detection (maybe move to FormAnalyzerAgent?)
            is_location_field = any(k in field_type.lower() for k in ['location', 'city', 'country', 'address']) or \
                                any(k in field_id.lower() for k in ['location', 'city', 'country', 'address'])
            
            if is_location_field:
                self.logger.info(f"Detected location field '{field_id}', using specialized location typeahead handler.")
                # We could still use strategy selector, but let it return a specific strategy
                # that delegates to this specialized handler.
                # strategy = await self.strategy_selector.select_strategy(element_data, value) 
                # if strategy == 'use_location_handler': ...
                # For now, directly call the specialized logic:
                return await self._execute_interactive_location_typeahead(context)
            else:
                self.logger.info(f"Using default typeahead handler for '{field_id}'")
                return await self._execute_default_typeahead_with_strategy(context)

        except ActionExecutionError as ae:
             self.logger.error(f"ActionExecutionError during typeahead action for {log_target}: {ae}")
             raise
        except Exception as e:
            self.logger.error(f"Unexpected error executing typeahead action for {log_target}: {e}", exc_info=True)
            raise ActionExecutionError(f"Failed to execute typeahead action for '{log_target}'") from e
            
    # --- Strategy Implementations --- 

    async def _execute_default_typeahead_with_strategy(self, context) -> bool:
        """Handles default typeahead interactions using strategies."""
        field_id = context.field_id
        field_value = str(context.field_value)
        frame_id = context.frame_id
        field_type = context.options.get('field_purpose') if context.options else None
        element_data = context.options.get("element_data") if context.options else None
        
        frame = await self._get_frame(frame_id)
        safe_selector = await self._sanitize_selector(field_id)

        # Ensure element is visible and interactable
        if not await self._ensure_element_visibility(frame, safe_selector):
            self.logger.error(f"Element {safe_selector} not visible for typeahead action.")
            return False
            
        self.logger.debug(f"Handling default typeahead for {safe_selector} with strategy selection")
        widget_type = element_data.get("widget_type", "autocomplete") # Default to autocomplete
        default_strategy = "type_and_select_fuzzy" 
        strategy = default_strategy
        possible_strategies = self.strategy_selector._get_possible_strategies(widget_type) if self.strategy_selector else [default_strategy]
        
        if self.strategy_selector and element_data:
            strategy = await self.strategy_selector.select_strategy(element_data, field_value)
            strategy = strategy if strategy in possible_strategies else default_strategy
        else:
            self.logger.warning(f"Skipping strategy selection for default typeahead.")
            
        self.logger.info(f"Using strategy '{strategy}' for default typeahead {safe_selector}")
        
        # Re-use the custom select interaction logic from SelectActionHandler helper
        # Map typeahead strategies to the parameters of _custom_select_interaction
        selection_made = False
        if strategy == "type_and_select_exact":
            selection_made = await self.select_helper._custom_select_interaction(frame, safe_selector, field_value, field_type, type_first=True, exact_match=True)
        elif strategy == "type_and_select_fuzzy":
            selection_made = await self.select_helper._custom_select_interaction(frame, safe_selector, field_value, field_type, type_first=True, exact_match=False)
        elif strategy == "fill_and_confirm":
            self.logger.info("Using 'fill_and_confirm' strategy: filling field and assuming confirmation.")
            selection_made = await self.form_interaction.fill_field(frame, safe_selector, field_value)
            if selection_made:
                await asyncio.sleep(0.5)
            # For fill_and_confirm, verification is tricky as the final value might be different
            # We rely on the initial fill success for this strategy.
            # We will still verify it below, but might log warnings if it doesn't match exactly.
        elif strategy == "clear_and_type_and_select":
            self.logger.info("Using 'clear_and_type_and_select' strategy.")
            if await self.form_interaction.clear_field(frame, safe_selector):
                 # Reuse custom select logic, defaulting to fuzzy match after clear+type
                 selection_made = await self.select_helper._custom_select_interaction(frame, safe_selector, field_value, field_type, type_first=True, exact_match=False)
            else:
                  self.logger.warning(f"Failed to clear field {safe_selector} for clear_and_type_and_select strategy.")
                  selection_made = False
        else:
             self.logger.warning(f"Unknown or invalid strategy '{strategy}' for default typeahead. Falling back to type_and_select_fuzzy.")
             selection_made = await self.select_helper._custom_select_interaction(frame, safe_selector, field_value, field_type, type_first=True, exact_match=False)

        # Add verification step
        if selection_made:
            self.logger.info(f"Default typeahead interaction attempt successful for '{safe_selector}', verifying...")
            # Use the verification logic from SelectActionHandler helper
            # Typeaheads are treated like custom selects (is_standard_select=False)
            # The expected value for verification should ideally be the *matched* value, 
            # but _custom_select_interaction doesn't return it directly. We'll verify against the original input field_value for now.
            # A better approach would be to modify _custom_select_interaction to return the matched text.
            return await self.select_helper._verify_selection(frame, safe_selector, field_value, is_standard_select=False)
        else:
            self.logger.error(f"Default typeahead interaction failed for strategy '{strategy}' on selector '{safe_selector}'.")
            return False

    async def _execute_interactive_location_typeahead(self, context) -> bool:
        """Handles location typeahead fields by typing parts and selecting matches."""
        field_id = context.field_id
        location_value = str(context.field_value)
        frame_id = context.frame_id
        field_type = "location" # Explicitly set
        element_data = context.options.get("element_data") if context.options else None

        frame = await self._get_frame(frame_id)
        safe_selector = await self._sanitize_selector(field_id)
        
        self.logger.info(f"Executing interactive location typeahead for {safe_selector} with value: {location_value}")

        if not await self._ensure_element_visibility(frame, safe_selector):
            self.logger.error(f"Location field {safe_selector} not visible")
            return False
            
        # Click to focus
        try:
            await frame.locator(safe_selector).click(timeout=1500)
        except Exception as e:
            self.logger.warning(f"Could not click {safe_selector} to activate location field: {e}")
            
        # Clear any existing content
        try:
            await frame.locator(safe_selector).fill("", timeout=2000)
            await asyncio.sleep(0.3)
        except Exception as e:
            self.logger.warning(f"Could not clear {safe_selector}: {e}")
            
        # Progressive typing steps
        parts = [part.strip() for part in location_value.split(',')] + [location_value] # Add full value as last step
        city = parts[0] if parts else location_value
        
        steps_to_try = []
        if len(city) >= 3: steps_to_try.append((city[:3], 400))
        if len(city) >= 5: steps_to_try.append((city[:5], 600))
        steps_to_try.append((city, 800))
        if len(parts) > 1: # If there's more than just a city (e.g., state, country)
             steps_to_try.append((location_value, 1000)) # Try typing the full string
             
        # Remove duplicates while preserving order
        seen_texts = set()
        unique_steps = []
        for text, wait_ms in steps_to_try:
             if text not in seen_texts:
                  unique_steps.append((text, wait_ms))
                  seen_texts.add(text)
                  
        success = False
        selected_text = None # Store the text that was actually selected
        for i, (text_to_type, wait_ms) in enumerate(unique_steps):
            self.logger.debug(f"Location typeahead step {i+1}/{len(unique_steps)}: Typing '{text_to_type}'")
            
            # Type the text
            await frame.locator(safe_selector).fill(text_to_type, timeout=3000)
            await asyncio.sleep(wait_ms / 1000.0)
            
            # TODO: Implement specific suggestion scraping for typeahead if needed,
            #       or rely on Playwright's auto-wait + semantic matching.
            # suggestions = await self.select_helper._scrape_visible_options(frame, safe_selector) # REMOVED reliance on SelectHandler helper
            # For now, assume suggestions might appear and proceed to match/select logic
            # We can refine scraping later if needed for specific complex typeaheads.
            suggestions = [] # Placeholder - semantic matching will try with empty list if no scraping done
            try:
                 # Quick check for common option roles after typing
                 suggestions = await frame.locator("[role='option']").all_text_contents(timeout=500)
            except Exception: 
                 self.logger.debug("Quick check for [role='option'] failed or timed out.")
                 # Consider adding more robust scraping here if the simple check fails often

            best_match_text = None
            if suggestions:
                self.logger.debug(f"Found {len(suggestions)} suggestions after typing '{text_to_type}': {suggestions[:5]}...")
                
                # Find the best match among suggestions for the *original* location_value
                # Match against the full original value, not just the current variant being typed
                best_match_text = None
                if self.strategy_selector:
                    # Generate variants using the static method from ActionStrategySelector
                    value_variants = ActionStrategySelector.generate_text_variants(location_value, field_type='location')
                    
                    best_match_text = await self.strategy_selector.find_best_match_semantic(
                        desired_value=location_value,
                        options=suggestions,
                        element_context=element_data,
                        value_variants=value_variants
                    )
                else:
                    self.logger.warning("StrategySelector not available, cannot perform semantic match for location.")
                
                if best_match_text:
                    self.logger.info(f"LLM found best suggestion match '{best_match_text}' for original location '{location_value}'")
                    # Use the helper from SelectActionHandler to find and click
                    # Note: This helper now returns bool for success
                    if await self.select_helper._find_and_click_option_by_text(frame, best_match_text):
                        self.logger.info(f"Successfully selected location option '{best_match_text}'")
                        selected_text = best_match_text # Store the selected text for verification
                        try: await frame.page.keyboard.press("Escape")
                        except Exception: pass
                        success = True
                        break # Exit loop on successful click
                    else:
                        self.logger.warning(f"Found location match '{best_match_text}' but failed to click. Trying keyboard nav.")
                else:
                     self.logger.debug("No suitable location match found in suggestions for this step.")
            else:
                 self.logger.debug("No suggestions found after typing this step.")
                 
            # Try basic keyboard navigation (Down+Enter)
            try:
                 await frame.locator(safe_selector).press("ArrowDown")
                 await asyncio.sleep(0.2)
                 await frame.locator(safe_selector).press("Enter")
                 self.logger.info("Attempted location selection via basic keyboard navigation (Down+Enter).")
                 # We don't know the exact text selected here, rely on final verification
                 success = True 
                 selected_text = None # Mark selected_text as unknown for verification
                 break # Exit loop
            except Exception as kb_err:
                 self.logger.warning(f"Basic keyboard nav failed: {kb_err}")
                
        # Final Verification step after the loop
        if success:
            # If we know the text we clicked, verify against that. Otherwise, verify against the original input.
            expected_verification_value = selected_text if selected_text is not None else location_value
            if selected_text is None:
                 self.logger.info(f"Location selection attempt made (keyboard nav or failed click), verifying final input against original value '{location_value}'...")
            else:
                 self.logger.info(f"Location selection attempt successful ('{selected_text}'), verifying final input...")
            
            # Call the verification method (re-using the one from SelectActionHandler)
            return await self.select_helper._verify_selection(frame, safe_selector, expected_verification_value, is_standard_select=False)
        else:
            self.logger.error(f"Interactive location typeahead failed for '{safe_selector}' after trying all steps.")
            # Final check / Fallback if loop finishes without success (moved inside else block)
            self.logger.warning(f"Checking final input value as last resort for {safe_selector}...")
            try:
                 final_value = await frame.locator(safe_selector).input_value()
                 norm_loc = ActionStrategySelector.normalize_text(location_value)
                 norm_final = ActionStrategySelector.normalize_text(final_value)
                 similarity = self.strategy_selector.calculate_similarity(norm_loc, norm_final) if self.strategy_selector else 0.0
                 if similarity > 0.6: # Keep lower threshold for this fallback
                      self.logger.info(f"Fallback check: Final value '{final_value}' in {safe_selector} seems plausible (Similarity: {similarity:.2f}). Returning True.")
                      return True
                 else:
                      self.logger.error(f"Fallback check: Final value '{final_value}' does not sufficiently match target '{location_value}' (Similarity: {similarity:.2f}). Returning False.")
                      return False
            except Exception as e_final:
                 self.logger.error(f"Could not get final value for fallback check on {safe_selector}: {e_final}")
                 return False # Fail if we can't even check the final state
                 
        return success # Return true if loop broke on success

    # --- Field Type Detection Helpers (Simplified from ActionExecutor) ---
    
    def _is_location_field(self, field_type, field_id, field_name, field_value) -> bool:
        """Checks if the field appears to be a location field."""
        if field_type == "location": return True
        
        name_id_combined = f"{(field_id or '').lower()} {(field_name or '').lower()}"
        if any(term in name_id_combined for term in ["location", "city", "state", "country", "address", "zip", "postal"]):
            return True
            
        # Check value patterns (e.g., "City, ST")
        if isinstance(field_value, str):
             if re.search(r"[A-Za-z ]+,\s*[A-Z]{2}\b", field_value):
                 self.logger.debug(f"Detected location field {field_id} based on city-state pattern in value")
                 return True
             # Add other location-like value checks if needed
             
        return False

    # def _is_demographic_field(self, field_type, field_id, field_name) -> bool:
    #     """Checks if the field appears to be a demographic field."""
    #     if field_type in ["gender", "race", "ethnicity", "hispanic", "veteran", "disability", "demographic"]:
    #         return True
        
    #     name_id_combined = f"{(field_id or '').lower()} {(field_name or '').lower()}"
    #     if any(term in name_id_combined for term in ["gender", "race", "ethnicity", "hispanic", "latino", "veteran", "disability", "demographic"]):
    #         return True
            
    #     return False 