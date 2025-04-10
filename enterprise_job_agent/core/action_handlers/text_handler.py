"""Handles text input actions."""
import logging
from typing import Dict, Any, Optional

from .base_handler import BaseActionHandler
# Assuming ActionContext and ActionExecutionError are defined elsewhere
# (e.g., in core or exceptions modules)
# from enterprise_job_agent.core.action_executor import ActionContext
from enterprise_job_agent.core.exceptions import ActionExecutionError
from enterprise_job_agent.core.browser_interface import BrowserInterface
from enterprise_job_agent.tools.form_interaction import FormInteraction
from enterprise_job_agent.tools.element_selector import ElementSelector
from enterprise_job_agent.core.action_strategy_selector import ActionStrategySelector
from enterprise_job_agent.core.diagnostics_manager import DiagnosticsManager
from thefuzz import fuzz
import traceback

class TextActionHandler(BaseActionHandler):
    """Handles text input actions like fill, email, password, textarea."""
    
    def __init__(
        self,
        browser_manager,
        form_interaction,
        element_selector,
        diagnostics_manager: Optional[DiagnosticsManager] = None,
        strategy_selector: Optional[ActionStrategySelector] = None
    ):
        """Initialize the handler with necessary components."""
        # Pass expected arguments to BaseActionHandler
        super().__init__(browser_manager, form_interaction, element_selector)
        self.form_interaction = form_interaction
        self.strategy_selector = strategy_selector
        self.diagnostics_manager = diagnostics_manager # Store diagnostics manager if needed
        self.logger = logging.getLogger(__name__) # Use standard logger
        if not self.strategy_selector:
            self.logger.warning("TextActionHandler initialized without an ActionStrategySelector. Strategy selection will be skipped.")
        # If diagnostics_manager is optional, add a similar check

    async def execute(self, context) -> bool:
        """Executes a text input action using a selected strategy."""
        self.logger.debug(f"HANDLER_CONTEXT_RECEIVED: TextHandler received context object id={id(context)} with field_id='{context.field_id}' and value='{context.field_value}'")
        selector = context.field_id
        value = context.field_value
        frame_id = context.frame_id
        element_data = context.options.get("element_data") if context.options else None
        scraped_options = element_data.get('options') if element_data else None
        widget_type = element_data.get('widget_type') if element_data else 'text_input' # Default if not present

        if not selector or value is None: # Allow empty string value
            self.logger.error(f"Missing selector ('{selector}') or value ('{value}') for text input.")
            return False

        # Check for None value before proceeding (early exit)
        if value is None:
            self.logger.warning(f"Skipping text input for '{selector}': Value is None.")
            return True # Treat as success (nothing to fill)

        # --- Strategy Determination --- 
        strategy = None
        success = False

        try:
            # 1. Prioritize Scraped Options if available
            if scraped_options and isinstance(scraped_options, list) and len(scraped_options) > 0:
                self.logger.info(f"Using pre-scraped options ({len(scraped_options)} found) for selector '{selector}'. Bypassing LLM strategy selection.")
                # Call the new method
                match_found = await self.form_interaction.select_option_from_list(selector, value, scraped_options, frame_id)
                # If a suitable match IS found in the list, assume we should proceed with a fill/type strategy
                # If NO match is found, we might still need to try filling the raw value (maybe it's free text?)
                if match_found:
                    # We found a match, but we still need to *fill* the input, potentially triggering selection.
                    # The best strategy here is often `type_and_select_fuzzy` or simply `fill`.
                    # Let's default to 'fill' for now, assuming the presence of options + match means it's a controlled input.
                    strategy = "fill" # Or maybe "type_and_select_fuzzy"?
                    self.logger.info(f"Match found in pre-scraped options. Proceeding with strategy: {strategy}")
                    # Don't return yet, fall through to execute the determined strategy.
                else:
                    # No match found in scraped options. This input might be free-form text despite having some options?
                    # Fall back to LLM/default strategy selection below.
                    self.logger.warning(f"No match found in pre-scraped list for '{selector}'. Falling back to LLM/default strategy selection.")
                    # Ensure strategy remains None so LLM/default logic runs
                    strategy = None

            # 2. Use LLM Strategy Selector ONLY if needed (no scraped options, scraped options failed match, or strategy not set above)
            if strategy is None: # Only run if strategy wasn't set by pre-scraped check
                if self.strategy_selector and element_data and widget_type in ['autocomplete', 'select_menu']: # Only call LLM for complex types
                    self.logger.debug(f"Invoking ActionStrategySelector for {selector} (widget: {widget_type})...")
                    strategy = await self.strategy_selector.select_strategy(element_data, value)
                    self.logger.info(f"LLM selected strategy: '{strategy}' for selector '{selector}'")
                else:
                    self.logger.debug(f"Skipping LLM strategy selection for {selector} (Widget: {widget_type}, Scraped Opts: {bool(scraped_options)}). Using default.")
            
                # Default strategy if LLM selection fails, is skipped, or wasn't needed
                # Use "type_and_select_fuzzy" as default for autocomplete, otherwise "fill"
                default_strategy = "type_and_select_fuzzy" if widget_type == 'autocomplete' else "fill"
                strategy = strategy or default_strategy # Use LLM strategy if available, else default
                
            # --- EXECUTION BASED ON DETERMINED STRATEGY --- #
            self.logger.info(f"Executing text input for '{selector}' using final strategy: {strategy}")
            
            # --- Need to use correct frame_id string for FormInteraction methods ---
            frame = await self._get_frame(frame_id) # Frame object for visibility checks
            safe_selector = await self._sanitize_selector(selector)
            await self._ensure_element_visibility(frame, safe_selector) # Use frame object here
            
            # Map strategy to FormInteraction method (pass frame_id string)
            if strategy == "fill":
                success = await self.form_interaction.fill_field(safe_selector, value, frame_id) # Pass frame_id string
            elif strategy == "type_and_select_exact":
                success = await self.form_interaction.type_and_select_option_exact(safe_selector, value, frame_id) # Pass frame_id string
            elif strategy == "type_and_select_fuzzy":
                success = await self.form_interaction.type_and_select_option_fuzzy(safe_selector, value, frame_id) # Pass frame_id string
            else:
                # Fallback strategy logic was moved up, this shouldn't be needed, but keep as safety
                self.logger.warning(f"Unknown or unsupported strategy '{strategy}' determined for text input {safe_selector}. Falling back to fill.")
                success = await self.form_interaction.fill_field(safe_selector, value, frame_id)

            # --- Final Outcome --- 
            if not success:
                strategy_logged = strategy # Log the strategy that was actually attempted
                self.logger.error(f"Text input failed for selector '{selector}' (Strategy attempted: '{strategy_logged}')")
                return False
                
            strategy_logged = strategy
            self.logger.info(f"Text input successful for '{selector}' (Strategy used: '{strategy_logged}')")
            return True
            
        except ActionExecutionError as ae:
             self.logger.error(f"ActionExecutionError during text input for {selector}: {ae}")
             raise
        except Exception as e:
            self.logger.error(f"Unexpected error during text input for {selector}: {e}", exc_info=True)
            raise ActionExecutionError(f"Failed to execute text input for '{selector}'") from e